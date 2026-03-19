# Patchright Migration Plan

Replace `playwright` + `playwright-stealth` with `patchright` for mobile browser sessions.

## Background

Mobile sessions currently use raw Playwright wrapped by playwright-stealth, plus a ~400-line custom JS injection script for fingerprint spoofing and anti-detection. This approach is fundamentally weak because:

1. Playwright leaks CDP `Runtime.enable` — the #1 bot detection signal
2. playwright-stealth patches at JS level, easily bypassed via iframes/stack traces
3. Fresh `browser.new_context()` behaves like incognito — detected by storage quota probes
4. Custom stealth args (`--no-sandbox`, `--disable-web-security`) are themselves detection signals

Patchright is a drop-in Playwright replacement that patches these at the driver/protocol level. With `launch_persistent_context` + `channel="chrome"`, it passes Cloudflare, Datadome, CreepJS, Fingerprint.com, Browserscan, etc.

---

## Scope

### In scope
- Replace playwright + playwright-stealth imports with patchright
- Switch from `browser.new_context()` to `launch_persistent_context()` for mobile
- Remove the custom JS fingerprint injection script (stealth portion)
- Remove stealth wrapper/application code from worker.py
- Update requirements.txt
- Update cleanup_browser to handle persistent context lifecycle
- Keep BrowserForge fingerprint generation for mobile context metadata (viewport, locale, timezone)

### Out of scope
- Desktop path (Camoufox) — untouched
- BrowserForge fingerprint generation logic (mobile.py) — untouched
- GeoIP module — untouched
- Activity/humanization modules — untouched (they use page/context API which is identical)
- Config schema changes — none needed

---

## File Change Map

| File | Change Type | Description |
|------|-------------|-------------|
| `app/browser/setup.py` | Major rewrite (mobile path) | Replace playwright/stealth with patchright, rewrite launch function, simplify injection script |
| `app/core/worker.py` | Minor edit | Remove stealth application block, adapt to persistent context (no `browser.new_context()` for mobile) |
| `requirements.txt` | Edit | Remove `playwright`, `playwright-stealth`, `humantyping[playwright]`. Add `patchright`. Change `humantyping[playwright]` to `humantyping` |
| `docs/issues/browser-detection-issues.md` | Update | Note patchright migration |

---

## Steps

### Step 1: Update requirements.txt

Remove:
```
playwright-stealth
```

Note: `playwright` must stay — camoufox imports from it internally.

Change:
```
humantyping[playwright]  -->  humantyping
```

Add:
```
patchright
```

Keep: `browserforge[all]`, `camoufox[geoip]`, `aiohttp` (all still needed).

Post-step: Run `pip install patchright && patchright install chrome`.

---

### Step 2: Rewrite `_launch_mobile_playwright_browser()` in setup.py

**Current** (lines 613-674): Launches Playwright via stealth wrapper, creates a bare browser instance, returns `(browser, stealth, stealth_kwargs)`.

**New**: Launch patchright with `launch_persistent_context()`. This returns a BrowserContext directly (not a Browser), which is the key API difference.

```python
async def _launch_mobile_patchright_context(
    headless_mode,
    proxy_cfg,
    worker_id,
    context_options,
):
    """Launch Patchright persistent context for mobile sessions."""
    from patchright.async_api import async_playwright

    pw = await async_playwright().start()

    launch_kwargs = {
        "user_data_dir": "",  # empty string = temp dir, cleaned up on close
        "channel": "chrome",
        "headless": False if headless_mode is False else True,
        "no_viewport": False,  # we DO want viewport control for mobile
    }

    # Merge mobile context options (viewport, locale, timezone, etc.)
    if context_options:
        for key in ("viewport", "locale", "timezone_id", "device_scale_factor",
                     "is_mobile", "has_touch", "extra_http_headers"):
            if key in context_options:
                launch_kwargs[key] = context_options[key]

    if proxy_cfg:
        launch_kwargs["proxy"] = proxy_cfg

    context = await pw.chromium.launch_persistent_context(**launch_kwargs)
    return context, pw
```

Key changes:
- No `Stealth()` wrapper — patchright handles stealth internally
- No `--no-sandbox`, `--disable-web-security` args — these are detection signals
- `launch_persistent_context` instead of `launch()` + `new_context()` — avoids incognito detection
- Returns `(context, pw)` instead of `(browser, stealth, stealth_kwargs)`
- `channel="chrome"` uses real Chrome, not Chromium

---

### Step 3: Rewrite mobile path in `configure_browser()`

**Current** (lines 854-1040): Generates fingerprint, maps to context_options, launches playwright+stealth browser, adds JS injection script, returns setup_result with browser/stealth/stealth_kwargs/injection_script.

**New**: Same fingerprint generation and context_options mapping, but:
- Call `_launch_mobile_patchright_context()` instead of `_launch_mobile_playwright_browser()`
- setup_result returns `"context"` directly (persistent context) instead of `"browser"`
- Remove `"stealth"`, `"stealth_kwargs"`, `"fingerprint_injection_script"` from setup_result
- Add `"is_persistent_context": True` flag so worker knows not to call `browser.new_context()`

What stays in context_options from BrowserForge fingerprint:
- `viewport` — set from fingerprint screen dimensions (NEW: currently not set, this fixes a bug)
- `locale` — from geoip or fingerprint
- `timezone_id` — from geoip
- `is_mobile: True`
- `has_touch: True`
- `device_scale_factor` — from fingerprint
- `extra_http_headers` — Accept-Language only (from geoip locale)

What gets removed:
- `user_agent` override — patchright best practice says do NOT set custom UA
- The entire `build_mobile_fingerprint_injection_script()` function (400 lines of JS)
- All stealth JS (webdriver hiding, CDP variable cleanup, storage faking, etc.)

---

### Step 4: Simplify `map_fingerprint_to_context_options()`

**Current** (lines 677-724): Maps fingerprint to context options but explicitly skips viewport dimensions.

**New**: Add viewport and device_scale_factor from fingerprint screen data:

```python
def map_fingerprint_to_context_options(fingerprint):
    if not isinstance(fingerprint, dict):
        return {}

    navigator = fingerprint.get("navigator")
    screen = fingerprint.get("screen", {})

    context_opts = {}
    context_opts["is_mobile"] = True
    context_opts["has_touch"] = True

    # Set viewport from fingerprint screen dimensions
    width = _fp_get(screen, "width", 412)
    height = _fp_get(screen, "height", 915)
    context_opts["viewport"] = {"width": int(width), "height": int(height)}

    dpr = _fp_get(screen, "devicePixelRatio")
    if dpr:
        context_opts["device_scale_factor"] = float(dpr)

    if lang := _fp_get(navigator, "language"):
        context_opts["locale"] = lang

    # DO NOT set user_agent — patchright works best with real Chrome UA
    # DO NOT set extra_http_headers with custom UA — same reason

    return context_opts
```

---

### Step 5: Update `cleanup_browser()` in setup.py

**Current** (lines 1047-1085): Closes contexts, closes browser, exits stealth manager and playwright.

**New**: Must handle two paths:
1. Desktop (Camoufox): unchanged — close contexts, close browser
2. Mobile (Patchright persistent context): close context directly, then stop playwright

Store `(pw_instance,)` in `_PLAYWRIGHT_MANAGERS` keyed by context id instead of browser id.

---

### Step 6: Update worker.py context creation

**Current** (lines 292-330):
```python
context_kwargs = dict(browser_setup.get("context_options") or {})
stealth = browser_setup.get("stealth")
stealth_kwargs = browser_setup.get("stealth_kwargs", {})
context = await browser.new_context(**context_kwargs)
if stealth:
    await stealth.apply_stealth_async(context)
fingerprint_injection_script = ...
if fingerprint_injection_script:
    await context.add_init_script(fingerprint_injection_script)
page = await context.new_page()
```

**New**:
```python
is_persistent = browser_setup.get("is_persistent_context", False)
if is_persistent:
    # Patchright mobile: context already created by launch_persistent_context
    context = browser_setup.get("context")
    # persistent context opens with one page already
    pages = context.pages
    page = pages[0] if pages else await context.new_page()
else:
    # Camoufox desktop: create context from browser as before
    context_kwargs = dict(browser_setup.get("context_options") or {})
    context = await browser.new_context(**context_kwargs)
    page = await context.new_page()
```

Remove entirely:
- stealth/stealth_kwargs extraction
- `stealth.apply_stealth_async(context)` block
- `fingerprint_injection_script` / `context.add_init_script()` block

---

### Step 7: Remove dead code from setup.py

Delete:
- `build_mobile_fingerprint_injection_script()` — entire function (~385 lines)
- `from playwright.async_api import async_playwright` (top-level import)
- `from playwright_stealth import Stealth` (top-level import)
- `_PLAYWRIGHT_MANAGERS` dict (replace with patchright-specific tracking)
- Stealth-related constants: none currently, but the `stealth_args` list inside the launch function
- `validate_fingerprint_consistency()` user_agent checks that no longer apply (optional, low priority)

Move patchright import inside function to keep it lazy (only loaded for mobile sessions).

---

### Step 8: Remove `humantyping[playwright]` extra

The `humantyping` package has a `[playwright]` extra that pulls in playwright. Change to bare `humantyping` in requirements.txt. Verify `app/navigation/referrer.py` still works — it only uses `HumanTyper` which is the core package, not the playwright integration.

---

## Risk Register

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `launch_persistent_context` with empty `user_data_dir` may behave differently across OS | Medium | Test on Windows; fall back to temp dir via `tempfile.mkdtemp()` if needed |
| Patchright `headless=True` is still detectable (author says use headful) | High | For servers, use virtual display (xvfb). For dev, use `headless=False`. Document in runbook |
| BrowserForge screen dimensions may not match real Chrome on mobile | Low | Use dimensions as viewport hint, let Chrome handle the rest |
| `humantyping` without `[playwright]` extra may break | Low | Test import in referrer.py; the core typing engine doesn't need playwright |
| Activity modules (scroll/hover/click) depend on page API | None | Patchright page API is identical to Playwright |
| `process_ads_tabs` and `natural_exit` use `context.pages` | None | Works identically on persistent context |

---

## Acceptance Criteria

1. Mobile sessions launch via patchright with `channel="chrome"`
2. No `playwright` or `playwright-stealth` imports remain in codebase
3. Desktop sessions still use Camoufox (unchanged)
4. Mobile sessions use persistent context (not `browser.new_context()`)
5. No custom JS fingerprint injection for stealth (patchright handles it)
6. Viewport, locale, timezone, touch settings still applied from BrowserForge + GeoIP
7. All existing activity modules (scroll, hover, click, ads) work without changes
8. `requirements.txt` has `patchright`, no `playwright` or `playwright-stealth`
9. Cleanup properly closes persistent context and stops patchright

---

## Execution Order

1. Step 1 (requirements.txt) + install patchright
2. Step 7 (delete dead code from setup.py — clean slate)
3. Step 2 (new launch function)
4. Step 3 (rewrite mobile path in configure_browser)
5. Step 4 (simplify context_options mapping)
6. Step 5 (update cleanup)
7. Step 6 (update worker.py)
8. Step 8 (humantyping extra)
9. Smoke test: run with `headless=False` and verify mobile session launches
