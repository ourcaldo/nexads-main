# AGENTS.md - nexAds

## Project Overview

nexAds is a Python browser automation tool for web traffic generation and ad interaction. It uses Camoufox (anti-detect Firefox via Playwright), multiprocessing for parallel workers, and asyncio for async browser operations within each worker. A PyQt5 GUI provides configuration editing.

## Repository Structure

```
main.py                      # Entry point: CLI arg parsing, launches GUI or automation
ui.py                        # Re-export shim for backward compat
config.json                  # Runtime configuration (JSON)
referrers.json               # Social media referrer domains
proxy.txt                    # Proxy list (user:pass@host:port)
requirements.txt             # pip dependencies (no pyproject.toml)
app/
  core/
    automation.py             # nexAds class: config loading, session distribution, worker orchestration
    worker.py                 # WorkerContext dataclass, worker_session() async loop, run_worker() entry
  browser/
    setup.py                  # configure_browser(), cleanup_browser() via Camoufox
    activities.py             # Human-like activities: scroll, hover, click
  ads/
    adsense.py                # AdSense detection, interaction, vignette handling, smart_click
  navigation/
    referrer.py               # Organic search, Google cookies, GDPR consent, social referrers
    tabs.py                   # Tab management: ensure_correct_tab, process_ads_tabs, natural_exit
    urls.py                   # URL navigation: extract_domain, navigate_to_url_by_click
  ui/
    config_window.py          # PyQt5 ConfigWindow (dark mode, 3 tabs)
.archive/legacy/main.py      # Pre-refactor monolithic original (reference only)
```

## Build / Run / Test Commands

### Installation
```bash
pip install -r requirements.txt
python -m camoufox fetch
patchright install chrome
```

### Running
```bash
python main.py               # Run automation (reads config.json)
python main.py --config      # Open PyQt5 configuration GUI
```

### Testing
No test framework is configured. No tests exist. If adding tests, use `pytest`:
```bash
pip install pytest pytest-asyncio
pytest                        # Run all tests
pytest tests/test_foo.py      # Run a single test file
pytest tests/test_foo.py::test_bar  # Run a single test function
pytest -k "keyword"           # Run tests matching a keyword
```

### Linting / Formatting
No linter or formatter is configured. If adding tooling, use `ruff`:
```bash
pip install ruff
ruff check .                  # Lint
ruff format .                 # Format
```

### Syntax Check (no deps needed)
```bash
python -m py_compile app/core/worker.py    # Check single file syntax
python -c "import ast; ast.parse(open('app/core/worker.py').read())"
```

## Agent Behaviour

### Git Commit Scope Rules
- Always commit and push after every change, including very small changes.
- For each commit/push, include all non-cache changes in the working tree by default.
- Exclude all Python cache artifacts under `__pycache__/` and `*.pyc` unless the user explicitly asks to include them.
- Stage files explicitly; do not use broad staging that can include secrets or generated files by accident.

### Change Log Rules
- For every implementation/change, update `docs/log/log-changes.md` before commit/push.
- Each log entry must include exactly these fields:
  - `Date time`
  - `Short description`
  - `What you do`
  - `File path that changes`
- Log entries should be appended in reverse-chronological order (newest first).

### Planning Rule
When a user asks for a plan, write a comprehensive markdown file with step-by-step tasks, goals, and acceptance criteria. Store plans in `docs/plans/` with clear structure and detail. Do not execute code until explicitly told to implement.

### Project-Specific Note
- `config.json` is a user-managed runtime file and should be included in commits when the user asks to push all non-cache changes.

---

## Code Style Guidelines

### Imports
- **Order:** stdlib first, then third-party, then local (`app.*`). Separate groups with one blank line.
- **Local imports use absolute paths:** `from app.browser.setup import configure_browser` (not relative).
- **Lazy/deferred imports** are used inside functions when a module is heavy or conditionally needed (e.g., PyQt5 is only imported when `--config` is passed).
- All `__init__.py` files are empty -- no barrel exports, no `__all__`.

### Naming
- **Functions/methods:** `snake_case` -- e.g., `configure_browser`, `perform_random_activity`
- **Variables:** `snake_case` -- e.g., `session_count`, `target_domain`
- **Classes:** `PascalCase` -- e.g., `WorkerContext`, `ConfigWindow`, `RateLimiter`
  - Exception: `nexAds` uses branded casing (intentional).
- **Constants:** `UPPER_SNAKE_CASE` -- e.g., `CONFIG_PATH`
- **Module-private constants:** prefixed with underscore -- e.g., `_PKG_ROOT`, `_REFERRERS_PATH`
- **Callback parameters:** suffixed with `_fn` -- e.g., `ensure_correct_tab_fn`, `smart_click_fn`, `extract_domain_fn`
- **Files:** `snake_case`, short single-word preferred -- e.g., `adsense.py`, `tabs.py`
- **Packages:** single lowercase word -- e.g., `core/`, `browser/`, `navigation/`

### Functions
- Most functions are `async def` (Playwright is async).
- Synchronous `def` only for pure utilities (`extract_domain`), file I/O (`get_social_referrer`), or multiprocessing entry points (`run_worker`).
- No arrow functions or lambda abuse -- lambdas only for sort keys, route interception, and activity selection closures.

### Type Annotations
- Minimal annotations. Annotate function parameters when the type is non-obvious: `worker_id: int`, `config: dict`, `target_url: str`.
- Return types are optional but encouraged for public functions: `-> bool`, `-> str`, `-> int`.
- Use `@dataclass` for structured data (see `WorkerContext`).
- Do not use complex generics, `TypedDict`, or `Protocol` -- keep it simple.

### Error Handling
- **Outer try/except pattern:** Wrap entire async function bodies in `try/except Exception as e` with a `print()` log and a safe return (`False`, `None`, `[]`).
- **Bare `except:` with `continue`** is used in loops over DOM elements where individual failures are expected and non-critical.
- **`SessionFailedException`** is raised to abort a session early; caught in the worker loop in `worker_session()`.
- **Never crash the worker.** Errors are logged and execution continues. Use `sys.exit(1)` only for truly fatal config errors in `main.py`.

### Logging
- All output via `print()` with a consistent prefix: `f"Worker {worker_id}: <message>"`.
- No `logging` module. Thread the `worker_id` through every function for traceability.

### Docstrings and Comments
- **Module-level docstrings** on all files: file path on first line, brief description on second.
- **Function docstrings:** single-line imperative mood -- e.g., `"""Detect if a vignette ad is showing."""`
- **Section headers** in long functions use `# --- SECTION NAME ---` format.
- **No TODO/FIXME markers** in production code.
- **`# noqa: F401`** for intentional unused re-exports (see `ui.py`).

### Dependency Injection Pattern
Functions accept dependencies as callback parameters (`_fn` suffix) rather than importing directly. The `worker_session()` function in `worker.py` is the **composition root** -- it creates bound closures over `WorkerContext` and passes them down:
```python
async def _ensure_tab(browser, page, url, wid, timeout=60):
    return await ensure_correct_tab(browser, page, url, wid, ctx.config, timeout)
```
Follow this pattern when adding new functionality that needs access to shared state.

### Concurrency Architecture
- **`multiprocessing.Process`** for parallelism (one process per worker).
- **`asyncio`** within each worker for async browser ops.
- **`run_worker()`** bridges sync/async: creates a new event loop per process.
- Shared state via `multiprocessing.Manager()` and `multiprocessing.Lock`.
- Windows-compatible: uses `freeze_support()` and `set_start_method('spawn')`.

### Configuration
- All config in `config.json`, loaded with `json.load()`.
- Config is a plain `dict` passed through function parameters.
- Use `.get(key, default)` for backward-compatible optional keys.
- Path resolution via `pathlib.Path(__file__).resolve().parent` chains.

### Browser Automation Conventions
- **Navigation:** `page.goto(url, timeout=90000, wait_until="networkidle")`
- **Element queries:** `page.query_selector_all('selector:visible')` with Playwright CSS selectors
- **Waits:** `page.wait_for_selector(selector, state="visible", timeout=45000)`
- **Delays:** `await asyncio.sleep(seconds)` or `await page.wait_for_timeout(milliseconds)`
- **Click fallback chain:** mouse click -> native `.click()` -> JS `evaluate("el.click()")`
- **Random human-like delays** injected everywhere via `random.randint()` / `random.uniform()`

### Mobile BrowserForge Fingerprint Reference (Required)
- Use BrowserForge `FingerprintGenerator` for mobile fingerprint requests when full payload is needed.
- Canonical generation command (Python):
```python
from browserforge.fingerprints import FingerprintGenerator
fp = FingerprintGenerator().generate(browser='chrome', os='android', device='mobile')
```
- For mobile fingerprint injection flows: **use the full payload**, not only user agent or a subset.
  - Required top-level sections to preserve and carry through: `headers`, `navigator`, `screen`, `battery`, `audioCodecs`, `videoCodecs`, `videoCard`, `pluginsData`, `multimediaDevices`, `fonts`.
  - Preserve full `navigator.userAgentData` and `navigator.extraProperties` if present.
  - Keep original header key casing and values from BrowserForge response.
  - Use the following full example payload structure for reference:
```json
{
  "audioCodecs": {
    "aac": "probably",
    "m4a": "maybe",
    "mp3": "probably",
    "ogg": "probably",
    "wav": "probably"
  },
  "battery": {
    "charging": false,
    "chargingTime": null,
    "dischargingTime": null,
    "level": 0.87
  },
  "fonts": [
    "sans-serif-thin"
  ],
  "headers": {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US;q=1.0",
    "Sec-Fetch-Dest": "navigate",
    "Sec-Fetch-Mode": "same-site",
    "Sec-Fetch-Site": "?1",
    "Sec-Fetch-User": "document",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"",
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": "\"Android\""
  },
  "mockWebRTC": false,
  "multimediaDevices": {
    "micros": [],
    "speakers": [],
    "webcams": [
      {
        "deviceId": "",
        "groupId": "",
        "kind": "videoinput",
        "label": ""
      }
    ]
  },
  "navigator": {
    "appCodeName": "Mozilla",
    "appName": "Netscape",
    "appVersion": "5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36",
    "deviceMemory": 8,
    "doNotTrack": null,
    "extraProperties": {
      "globalPrivacyControl": null,
      "installedApps": [],
      "pdfViewerEnabled": null,
      "vendorFlavors": [
        "chrome"
      ]
    },
    "hardwareConcurrency": 8,
    "language": "en-US",
    "languages": [
      "en-US"
    ],
    "maxTouchPoints": 5,
    "oscpu": null,
    "platform": "Linux armv81",
    "product": "Gecko",
    "productSub": "20030107",
    "userAgent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36",
    "userAgentData": {
      "architecture": "",
      "bitness": "",
      "brands": [
        {
          "brand": "Not)A;Brand",
          "version": "8"
        },
        {
          "brand": "Chromium",
          "version": "138"
        },
        {
          "brand": "Google Chrome",
          "version": "138"
        }
      ],
      "fullVersionList": [
        {
          "brand": "Not)A;Brand",
          "version": "8.0.0.0"
        },
        {
          "brand": "Chromium",
          "version": "138.0.7204.179"
        },
        {
          "brand": "Google Chrome",
          "version": "138.0.7204.179"
        }
      ],
      "mobile": true,
      "model": "V1818CA",
      "platform": "Android",
      "platformVersion": "8.1.0",
      "uaFullVersion": "138.0.7204.179"
    },
    "vendor": "Google Inc.",
    "vendorSub": null,
    "webdriver": false
  },
  "pluginsData": {
    "mimeTypes": [],
    "plugins": []
  },
  "screen": {
    "availHeight": 910,
    "availLeft": 0,
    "availTop": 0,
    "availWidth": 360,
    "clientHeight": 18,
    "clientWidth": 0,
    "colorDepth": 24,
    "devicePixelRatio": 1,
    "hasHDR": false,
    "height": 910,
    "innerHeight": 0,
    "innerWidth": 0,
    "outerHeight": 780,
    "outerWidth": 360,
    "pageXOffset": 0,
    "pageYOffset": 0,
    "pixelDepth": 24,
    "screenX": 0,
    "width": 360
  },
  "slim": false,
  "videoCard": {
    "renderer": "ANGLE (ARM, Mali-G51, OpenGL ES 3.2)",
    "vendor": "Google Inc. (ARM)"
  },
  "videoCodecs": {
    "h264": "probably",
    "ogg": "",
    "webm": "probably"
  }
}
```

### Dual-Browser Architecture (Critical)

Camoufox does NOT support mobile device emulation. The project uses two separate browser engines:

- **Desktop sessions**: Camoufox (anti-detect Firefox) — handles fingerprinting, geoip, humanization at engine level
- **Mobile sessions**: Patchright (undetected Chromium) — patched Playwright fork that avoids CDP detection leaks

#### Patchright (Mobile Engine)
- **What it is**: Drop-in replacement for Playwright that patches `Runtime.enable` CDP leaks, removes automation flags, and executes JS in isolated contexts to avoid bot detection.
- **Import**: `from patchright.async_api import async_playwright` (same API as Playwright)
- **Chromium only**: Firefox and WebKit are NOT supported by Patchright. This is fine since mobile sessions target Chrome/Android.
- **Best practice for maximum stealth**:
  - Use `launch_persistent_context()` with `channel="chrome"` and `headless=False` (use virtual display on servers)
  - Do NOT inject custom User-Agent or browser headers — let the real Chrome identity through
  - Patchright automatically handles: `navigator.webdriver=false`, automation flag removal, extension enablement
- **playwright-stealth is NOT used**: Patchright replaces both `playwright` and `playwright-stealth`. The stealth is built into the driver itself at a deeper level than JS-based patches.
- **Install**: `pip install patchright` then `patchright install chrome`
- **Passes**: Cloudflare, Datadome, Kasada, Akamai, CreepJS, Fingerprint.com, Sannysoft, Browserscan (97%), Pixelscan, IPHey

#### Patchright Stealth Rules (PROVEN — do not violate)
These rules were tested and validated on 2026-03-19. Violating them causes detection regressions.

1. **Do NOT inject custom User-Agent via CDP or context options** — `Emulation.setUserAgentOverride` does not propagate to Web Workers. Detection scripts compare main page vs Worker UA and flag the mismatch (`hasInconsistentWorkerValues`). This applies to ALL CDP-based UA/platform/userAgentData overrides.
2. **Do NOT use `add_init_script` for navigator prototype overrides** — Patchright runs init scripts in an isolated context. Overrides to `Navigator.prototype` (platform, maxTouchPoints, plugins, pdfViewerEnabled) do NOT affect the main world. Only instance-level properties on shared objects (window, navigator instance) work.
3. **Do NOT use `Page.addScriptToEvaluateOnNewDocument` via CDP** — Also runs in isolated context in patchright, same limitation as add_init_script.
4. **Do NOT intercept HTML responses to inject scripts** — Route-based `<script>` injection into HTML causes WebGL exceptions and request failures. Also detectable via CSP and response integrity checks.
5. **ONLY set these context options for mobile**: `viewport`, `locale`, `timezone_id`, `is_mobile`, `has_touch`, `device_scale_factor`, `extra_http_headers` (Accept-Language only).
6. **WebRTC prevention works**: `--webrtc-ip-handling-policy=disable_non_proxied_udp` successfully prevents real IP leak via WebRTC when proxy is configured.
7. **DNS-over-HTTPS via Chrome flags**: `--dns-over-https-mode=secure` with Cloudflare template is set but browserscan still flags DNS leak with HTTP proxy. SOCKS5 without auth would fix it but Chromium doesn't support SOCKS5 with auth.

#### Known Limitations (cannot be fixed with patchright)
- **Platform shows real OS** (Windows/Linux) — cannot spoof `navigator.platform` without triggering Worker inconsistency detection. Camoufox handles this at engine level but doesn't support mobile.
- **WebGL shows real GPU** — cannot override `WebGLRenderingContext.getParameter` in main world from patchright's isolated context. Route injection works but causes WebGL exceptions.
- **`hasInconsistentWorkerValues`** — `navigator.maxTouchPoints` is `undefined` in Web Workers but `0`/`1` in main page. This is standard Chromium behavior, affects even manual Chrome usage. Browserscan false positive.
- **DNS leak (-3%)** — HTTP proxies don't tunnel DNS. Only SOCKS5 (without auth) fixes this.
- **Best achievable score**: 97% on browserscan.net with HTTP proxy.

#### Key Architectural Rule
- Never use raw `playwright` or `playwright-stealth` for any browser session. Desktop uses Camoufox. Mobile uses Patchright.
- BrowserForge fingerprints are used for mobile context metadata (viewport, locale, touch, DPR) but NOT for identity spoofing (UA, platform, WebGL). Patchright's stealth works best with clean, real Chrome identity.

#### Browser Module Structure
```
app/browser/
  setup.py          # Thin orchestrator (~69 lines): picks desktop or mobile, delegates
  proxy.py          # Proxy string parsing and config resolution (shared)
  desktop.py        # Camoufox launch + cleanup
  mobile.py         # Patchright launch/cleanup + BrowserForge fingerprint + mapping + validation
  activities.py     # Human-like scroll, hover, click
  humanization.py   # Mouse movement, timing helpers
  geoip.py          # Proxy IP geolocation lookup
```

### Known Issues / Tech Debt
- `RateLimiter` class in `automation.py` is defined but `wait_if_needed()` is never called anywhere.
