# Migration Plan: Patchright to CloakBrowser for Mobile Sessions

**Date:** 2026-03-20
**Status:** Implemented (Phase 1-4 complete, Phase 5 deploy pending)
**Replaces:** `docs/plans/2026-03-19-patchright-migration.md` (Patchright is now being replaced)

## Background

Patchright achieves 97% on BrowserScan but is **detected as a bot** — the most critical failure. The core issue is Chromium's CDP limitations: UA/platform overrides don't propagate to Web Workers, causing `hasInconsistentWorkerValues` detection. This is unfixable at the CDP layer.

CloakBrowser is a custom Chromium binary with 33 source-level C++ patches. It scores lower on BrowserScan (~67-77%) due to audio/incognito/DNS issues, but crucially: **Bot Detection: No Detection** and **consistent platform identity** (no Worker mismatches). Source-level patches bypass all CDP limitations.

### Decision
- **Desktop:** Keep Camoufox (97% score, not detected as bot, proven stable)
- **Mobile:** Replace Patchright + BrowserForge with CloakBrowser

## Goals

1. Replace Patchright with CloakBrowser as the mobile browser engine
2. Eliminate BrowserForge fingerprint generation/validation pipeline (CloakBrowser handles fingerprints at binary level)
3. Maintain the same worker contract (`{context, is_persistent_context: True}`)
4. No changes to worker.py, navigation, activities, or ads code
5. Add CloakBrowser binary to server setup script

## Acceptance Criteria

- [ ] Mobile sessions launch via CloakBrowser `launch_persistent_context_async()`
- [ ] Bot detection passes on browserscan.net (No Detection)
- [ ] Platform identity is consistent (no OS mismatch)
- [ ] GeoIP timezone/locale auto-detection works via CloakBrowser's `geoip=True`
- [ ] Proxy authentication works with CloakBrowser's proxy string format
- [ ] Cleanup properly closes context (with timeout fallback)
- [ ] Desktop path (Camoufox) is completely unchanged
- [ ] Fallback to desktop works when CloakBrowser launch fails
- [ ] All 10 fleet servers deploy and run successfully
- [ ] `patchright` removed from requirements.txt, `cloakbrowser[geoip]` added

## Current Architecture

```
setup.py (orchestrator)
  |
  +-- device_type == "desktop" --> desktop.py (Camoufox)
  |     - launch_desktop_browser() returns {browser, is_persistent_context: False}
  |     - Worker creates context from browser, then page from context
  |
  +-- device_type == "mobile" --> mobile.py (Patchright + BrowserForge)
        - BrowserForge generates fingerprint (~100 lines)
        - Validates fingerprint consistency (~60 lines)
        - Maps fingerprint to context options (~30 lines)
        - Our geoip.py does IP lookup, overrides locale/timezone
        - Patchright launches persistent context
        - Returns {context, is_persistent_context: True}
        - Worker sets browser = context, uses context.pages[0]
```

### Files Involved
| File | Role | Lines |
|------|------|-------|
| `app/browser/mobile.py` | Patchright + BrowserForge launch/cleanup/fingerprint | ~620 |
| `app/browser/setup.py` | Orchestrator, picks desktop vs mobile | ~70 |
| `app/browser/proxy.py` | Proxy parsing, `resolve_proxy_config()`, `build_full_proxy_url()` | ~142 |
| `app/browser/geoip.py` | GeoIP lookup via proxy IP | ~371 |
| `app/core/worker.py` | Consumes setup result, handles persistent context | ~970 |

### Worker Contract (must not change)
`configure_mobile_browser()` returns:
```python
{
    "browser": None,
    "context": <playwright BrowserContext>,
    "context_options": {},
    "fingerprint_mode": "mobile",
    "fallback_reason": "",
    "validation_reason_codes": [],
    "is_persistent_context": True,
}
```
Worker (lines 358-365) checks `is_persistent_context`, sets `browser = context`, gets first page.

## Target Architecture

```
setup.py (orchestrator) — minimal comment changes
  |
  +-- device_type == "desktop" --> desktop.py (Camoufox) — UNCHANGED
  |
  +-- device_type == "mobile" --> mobile.py (CloakBrowser) — REWRITTEN
        - Build proxy URL string from proxy_cfg dict
        - Call launch_persistent_context_async() with:
          - Android fingerprint flags (platform, GPU, screen)
          - Mobile viewport, UA, is_mobile, has_touch
          - geoip=True for timezone/locale
          - storage quota flag for incognito mitigation
        - Return same contract {context, is_persistent_context: True}
```

## Implementation Tasks

### Phase 1: Rewrite `app/browser/mobile.py`

**Goal:** Replace ~620 lines of Patchright + BrowserForge with ~100 lines of CloakBrowser.

#### Task 1.1: New `configure_mobile_browser()`
- Accept same parameters: `config, headless, proxy_cfg, worker_id, get_random_delay_fn`
- Convert `proxy_cfg` dict (`{server, username, password}`) to CloakBrowser string format (`http://user:pass@host:port`) using `build_full_proxy_url()` from proxy.py
- Determine headless mode: CloakBrowser uses `headless=True/False` (no "virtual" — servers use Xvfb with `headless=False`)
- Generate random fingerprint seed per session
- Call `launch_persistent_context_async()` with:
  ```python
  context = await launch_persistent_context_async(
      user_data_dir=tempfile.mkdtemp(prefix="nexads_mobile_"),
      headless=False,  # servers use Xvfb
      proxy=proxy_url,
      geoip=True,
      viewport={"width": 412, "height": 915},
      user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.7632.159 Mobile Safari/537.36",
      is_mobile=True,
      has_touch=True,
      device_scale_factor=2.625,
      args=[
          "--fingerprint-platform=android",
          "--fingerprint-gpu-vendor=Qualcomm",
          "--fingerprint-gpu-renderer=ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)",
          "--fingerprint-screen-width=412",
          "--fingerprint-screen-height=915",
          "--fingerprint-storage-quota=5000",
          "--fingerprint-hardware-concurrency=8",
          "--fingerprint-device-memory=8",
      ],
  )
  ```
- Return same contract dict with `is_persistent_context: True`
- Keep telemetry events (`emit_mobile_fingerprint_event`) for observability

#### Task 1.2: New `cleanup_mobile_context()`
- CloakBrowser's `context.close()` internally stops playwright and cleans up
- Wrap in `asyncio.wait_for(timeout=15)` for safety
- Delete temp user_data_dir after close
- Track temp dirs for cleanup (simpler than current `_PATCHRIGHT_MANAGERS` dict)

#### Task 1.3: Delete removed code
- Delete: `generate_mobile_fingerprint()`, `get_fingerprint_summary()`, `map_fingerprint_to_context_options()`, `validate_fingerprint_consistency()`, `launch_mobile_context()`, `_fp_get()`, `_to_plain()`, `parse_mobile_constraints()`, `select_mobile_fingerprint_params()`
- Delete: `_PATCHRIGHT_MANAGERS` dict, `MOBILE_FINGERPRINT_*` constants
- Delete: `browserforge.fingerprints` import
- Keep: `emit_mobile_fingerprint_event` import for telemetry

### Phase 2: Update `app/browser/setup.py`

**Goal:** Update comments, no logic changes.

#### Task 2.1: Update module docstring and comments
- Change "Patchright" references to "CloakBrowser"
- Comment on line 37: "Mobile path: CloakBrowser"
- No import changes needed — same function names exported from mobile.py

### Phase 3: Update AGENTS.md

**Goal:** Document new architecture.

#### Task 3.1: Update Dual-Browser Architecture section
- Replace Patchright references with CloakBrowser
- Remove "Patchright Stealth Rules" section (no longer applies)
- Remove "Known Limitations (cannot be fixed with patchright)" section
- Add CloakBrowser section with flags reference and known limitations
- Update Browser Module Structure description
- Remove BrowserForge fingerprint reference section (no longer used for mobile)

### Phase 4: Dependencies

**Goal:** Swap patchright for cloakbrowser in requirements.

#### Task 4.1: Update `requirements.txt`
- Remove: `patchright`
- Add: `cloakbrowser[geoip]`
- Keep: `browserforge` (still used by Camoufox for `Screen`)
- Keep: `playwright` (still used by Camoufox)

#### Task 4.2: Update `scripts/setup_ubuntu.sh`
- Add after pip install: `python3 -m cloakbrowser install` (downloads 199MB binary)
- Remove: `patchright install chrome`
- Keep: `playwright install firefox` (for Camoufox)

### Phase 5: Deploy

**Goal:** Roll out to all fleet servers.

#### Task 5.1: Commit and push
- Update `docs/log/log-changes.md`
- Commit all changes
- Push to origin/main

#### Task 5.2: Deploy to fleet
- `./scripts/nexads-remote.sh all stop`
- `./scripts/nexads-remote.sh all deploy` (runs setup_ubuntu.sh which installs cloakbrowser + binary)
- `./scripts/nexads-remote.sh all start`
- `./scripts/nexads-remote.sh all status` to verify

## What Does NOT Change

| Component | Why |
|-----------|-----|
| `app/core/worker.py` | Same contract: checks `is_persistent_context`, sets `browser = context` |
| `app/browser/desktop.py` | Camoufox desktop path untouched |
| `app/browser/proxy.py` | Still used for `resolve_proxy_config()` and `build_full_proxy_url()` |
| `app/browser/geoip.py` | Still used for proxy URL building; CloakBrowser handles geoip internally |
| `app/browser/activities.py` | No browser-engine-specific code |
| `app/browser/humanization.py` | No browser-engine-specific code |
| `app/navigation/*` | All navigation code is browser-agnostic (uses Playwright API) |
| `app/ads/*` | All ad code is browser-agnostic |
| `config.json` | No new config keys needed |

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CloakBrowser binary download fails on server | Mobile sessions fall back to desktop | setup.py already has fallback: `if result is None: return await launch_desktop_browser()` |
| CloakBrowser binary is 199MB per server | One-time download, cached | Pre-download in `setup_ubuntu.sh`, binary is cached in `~/.cloakbrowser/` |
| `--fingerprint-platform=android` doesn't fully spoof on Linux | `navigator.platform` shows `Linux x86_64` instead of `Linux armv8l` | Tested: BrowserScan still shows "No Detection" for bot check. Platform mismatch costs -5% but bot evasion is the priority |
| Incognito detection on Linux Xvfb | -10% on BrowserScan | `--fingerprint-storage-quota=5000` mitigates. Confirmed working in issue #46 on Docker+Xvfb |
| Audio exception on CloakBrowser | -5% on BrowserScan | Binary-level patch issue, cannot fix from our side. Does not affect bot detection score |
| CloakBrowser Playwright version mismatch with Camoufox | Import conflicts | Both use standard Playwright API. CloakBrowser bundles its own binary, Camoufox bundles its own. No conflict |

## Mobile Device Profiles

For Phase 1, use a single hardcoded Pixel 8 profile. Future enhancement: randomize from a pool.

```
Device: Google Pixel 8
OS: Android 14
Screen: 412x915 @ 2.625x DPR
GPU: Qualcomm Adreno 730 (OpenGL ES 3.2)
UA: Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.7632.159 Mobile Safari/537.36
```

## CloakBrowser Flags Reference

| Flag | Value | Purpose |
|------|-------|---------|
| `--fingerprint=<seed>` | Random int per session | Deterministic fingerprint (canvas, WebGL, audio, fonts) |
| `--fingerprint-platform=android` | Fixed | Navigator.platform, UA OS |
| `--fingerprint-gpu-vendor=Qualcomm` | Fixed | WebGL UNMASKED_VENDOR |
| `--fingerprint-gpu-renderer=ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)` | Fixed | WebGL UNMASKED_RENDERER |
| `--fingerprint-screen-width=412` | Fixed | screen.width |
| `--fingerprint-screen-height=915` | Fixed | screen.height |
| `--fingerprint-storage-quota=5000` | Fixed | Bypass incognito detection (BrowserScan) |
| `--fingerprint-hardware-concurrency=8` | Fixed | navigator.hardwareConcurrency |
| `--fingerprint-device-memory=8` | Fixed | navigator.deviceMemory |
| `geoip=True` | Param | Auto-detect timezone + locale from proxy IP |

## Estimated Scope

| Phase | Files Changed | Effort |
|-------|---------------|--------|
| Phase 1: Rewrite mobile.py | 1 file (~620 lines deleted, ~100 lines new) | Primary |
| Phase 2: Update setup.py | 1 file (comments only) | Trivial |
| Phase 3: Update AGENTS.md | 1 file (documentation) | Small |
| Phase 4: Dependencies | 2 files (requirements.txt, setup_ubuntu.sh) | Small |
| Phase 5: Deploy | 0 files (operational) | Script-driven |

Total: 5 files changed, net reduction of ~500 lines of code.
