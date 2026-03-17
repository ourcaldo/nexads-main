# Refactoring Plan: Single-File → Python Package Structure

## Overview

Migrate `nexads` from two monolithic files (`main.py` ~1844 lines, `ui.py` ~878 lines) into a proper Python package structure for maintainability, testability, and clarity.

---

## Target Structure

```
nexads/
├── main.py                        # Entry point only (~25 lines)
├── nexads/                        # Main package
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── automation.py          # nexAds class, RateLimiter, start/stop, session distribution
│   │   └── worker.py              # WorkerContext, worker_session, run_worker, run_worker_async
│   ├── browser/
│   │   ├── __init__.py
│   │   ├── setup.py               # configure_browser, cleanup_browser
│   │   └── activities.py          # random_scroll, random_hover, random_click,
│   │                              # perform_random_activity, add_cursor_trail
│   ├── navigation/
│   │   ├── __init__.py
│   │   ├── tabs.py                # ensure_correct_tab, process_ads_tabs, natural_exit
│   │   ├── referrer.py            # get_random_keyword, perform_organic_search,
│   │   │                          # social/direct referrer logic
│   │   └── urls.py                # navigate_to_url_by_click, random_navigation, extract_domain
│   ├── ads/
│   │   ├── __init__.py
│   │   └── adsense.py             # detect_adsense_ads, interact_with_ads,
│   │                              # detect_vignette_ad, interact_with_vignette_ad,
│   │                              # check_and_handle_vignette
│   └── ui/
│       ├── __init__.py
│       └── config_window.py       # Full ConfigWindow class (moved from ui.py)
├── config.json
├── referrers.json
├── requirements.txt
└── docs/
    ├── issues.md
    └── plans/
        └── refactor-package-structure.md
```

---

## Function/Class Mapping

### `main.py` (current) → new locations

| Symbol | New Location |
|---|---|
| `SessionFailedException` | `nexads/core/automation.py` |
| `RateLimiter` | `nexads/core/automation.py` |
| `nexAds.__init__` | `nexads/core/automation.py` |
| `nexAds.calculate_session_distribution` | `nexads/core/automation.py` |
| `nexAds.load_config` | `nexads/core/automation.py` |
| `nexAds.get_random_delay` | `nexads/core/automation.py` |
| `nexAds.start` | `nexads/core/automation.py` |
| `nexAds.stop` | `nexads/core/automation.py` |
| `nexAds.configure_browser` | `nexads/browser/setup.py` |
| `nexAds.cleanup_browser` | `nexads/browser/setup.py` |
| `nexAds.perform_random_activity` | `nexads/browser/activities.py` |
| `nexAds.random_scroll` | `nexads/browser/activities.py` |
| `nexAds.random_hover` | `nexads/browser/activities.py` |
| `nexAds.random_click` | `nexads/browser/activities.py` |
| `nexAds.add_cursor_trail` | `nexads/browser/activities.py` |
| `nexAds.extract_domain` | `nexads/navigation/urls.py` |
| `nexAds.navigate_to_url_by_click` | `nexads/navigation/urls.py` |
| `nexAds.random_navigation` | `nexads/navigation/urls.py` |
| `nexAds.get_random_keyword` | `nexads/navigation/referrer.py` |
| `nexAds.perform_organic_search` | `nexads/navigation/referrer.py` |
| `nexAds.accept_google_cookies` | `nexads/navigation/referrer.py` |
| `nexAds.handle_gdpr_consent` | `nexads/navigation/referrer.py` |
| `nexAds.setup_request_interceptor` | `nexads/navigation/referrer.py` |
| `nexAds.ensure_correct_tab` | `nexads/navigation/tabs.py` |
| `nexAds.process_ads_tabs` | `nexads/navigation/tabs.py` |
| `nexAds.natural_exit` | `nexads/navigation/tabs.py` |
| `nexAds.detect_adsense_ads` | `nexads/ads/adsense.py` |
| `nexAds.interact_with_ads` | `nexads/ads/adsense.py` |
| `nexAds.detect_vignette_ad` | `nexads/ads/adsense.py` |
| `nexAds.interact_with_vignette_ad` | `nexads/ads/adsense.py` |
| `nexAds.check_and_handle_vignette` | `nexads/ads/adsense.py` |
| `nexAds.smart_click` | `nexads/ads/adsense.py` |
| `nexAds.worker_session` | `nexads/core/worker.py` |
| `run_worker_async` | `nexads/core/worker.py` |
| `run_worker` | `nexads/core/worker.py` |
| `main` | `main.py` (root entry point) |

### `ui.py` (current) → new location

| Symbol | New Location |
|---|---|
| `ConfigWindow` (entire class) | `nexads/ui/config_window.py` |

---

## Shared State Strategy

The biggest challenge is that all methods currently live on the `nexAds` class and share `self.config`, `self.lock`, `self.running`, `self.rate_limiter`, etc.

### Solution: `WorkerContext` dataclass

Create a `WorkerContext` dataclass in `nexads/core/worker.py` that bundles all shared state and is passed to every function that needs it:

```python
# nexads/core/worker.py
from dataclasses import dataclass
from typing import Any
import multiprocessing

@dataclass
class WorkerContext:
    config: dict
    lock: multiprocessing.Lock
    running: bool
    rate_limiter: Any          # RateLimiter instance
    ads_session_flags: list
    pending_ads_sessions: int
```

Functions in `browser/`, `navigation/`, `ads/` accept `ctx: WorkerContext` as their first argument instead of `self`. This removes the circular dependency of having every module import the `nexAds` class.

### Config file paths

Use `pathlib` to resolve paths relative to the package root, not the working directory:

```python
# nexads/core/automation.py
import pathlib

_PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CONFIG_PATH    = _PKG_ROOT / "config.json"
REFERRERS_PATH = _PKG_ROOT / "referrers.json"
```

---

## Import Dependency Graph

To avoid circular imports, each module only imports from levels below it:

```
main.py
  └── nexads.core.automation (nexAds, RateLimiter)
        └── nexads.core.worker (WorkerContext, run_worker)
              ├── nexads.browser.setup
              ├── nexads.browser.activities
              ├── nexads.navigation.tabs
              ├── nexads.navigation.referrer
              ├── nexads.navigation.urls
              └── nexads.ads.adsense
                    └── nexads.browser.activities (smart_click used by ads)
```

**Key rule:** No module in `browser/`, `navigation/`, or `ads/` imports from `core/`. They only receive `WorkerContext` as a parameter.

---

## Implementation Steps

### Step 0 — Snapshot
- Commit current working state to git before touching anything
- Run `python main.py --config` to confirm GUI opens (baseline)

### Step 1 — Create directory skeleton
Create all directories and empty `__init__.py` files:
```
nexads/__init__.py
nexads/core/__init__.py
nexads/browser/__init__.py
nexads/navigation/__init__.py
nexads/ads/__init__.py
nexads/ui/__init__.py
```
Do **not** move any code yet.

### Step 2 — Move UI
- Copy `ConfigWindow` class from `ui.py` → `nexads/ui/config_window.py`
- Update root `ui.py` to simply re-export: `from nexads.ui.config_window import ConfigWindow`
- Verify: `python main.py --config` still opens GUI ✅

### Step 3 — Move browser setup
- Move `configure_browser`, `cleanup_browser` → `nexads/browser/setup.py`
- These become standalone `async` functions accepting `(config: dict, worker_id: int)`
- Add stub methods on `nexAds` that delegate to these functions
- Verify: no import errors ✅

### Step 4 — Move browser activities
- Move `random_scroll`, `random_hover`, `random_click`, `perform_random_activity`, `add_cursor_trail` → `nexads/browser/activities.py`
- Functions accept `(page, browser, worker_id, config, ...)` — no `self`
- Verify: no import errors ✅

### Step 5 — Move URL navigation
- Move `extract_domain`, `navigate_to_url_by_click`, `random_navigation` → `nexads/navigation/urls.py`
- Verify: no import errors ✅

### Step 6 — Move referrer logic
- Move `get_random_keyword`, `perform_organic_search`, `accept_google_cookies`, `handle_gdpr_consent`, `setup_request_interceptor` → `nexads/navigation/referrer.py`
- Verify: no import errors ✅

### Step 7 — Move tab management
- Move `ensure_correct_tab`, `process_ads_tabs`, `natural_exit` → `nexads/navigation/tabs.py`
- Verify: no import errors ✅

### Step 8 — Move ads logic
- Move `detect_adsense_ads`, `interact_with_ads`, `detect_vignette_ad`, `interact_with_vignette_ad`, `check_and_handle_vignette`, `smart_click` → `nexads/ads/adsense.py`
- `smart_click` calls `add_cursor_trail` — import from `nexads.browser.activities`
- Verify: no import errors ✅

### Step 9 — Move worker logic
- Move `worker_session`, `run_worker_async`, `run_worker` → `nexads/core/worker.py`
- Introduce `WorkerContext` dataclass here
- Verify: no import errors ✅

### Step 10 — Finalize core automation
- `nexads/core/automation.py` keeps: `nexAds`, `RateLimiter`, `SessionFailedException`
- `nexAds` methods now delegate to functions in submodules
- Remove all moved method bodies from `nexAds`
- Verify: full run works end-to-end ✅

### Step 11 — Slim down root `main.py`
```python
# main.py
import sys
import multiprocessing
from argparse import ArgumentParser
from PyQt5.QtWidgets import QApplication
from nexads.core.automation import nexAds
from nexads.ui.config_window import ConfigWindow

def main():
    parser = ArgumentParser(description='nexAds Automation Tool')
    parser.add_argument('--config', action='store_true', help='Open configuration GUI')
    args = parser.parse_args()

    if args.config:
        app = QApplication(sys.argv)
        window = ConfigWindow()
        window.show()
        sys.exit(app.exec_())
    else:
        automation = nexAds()
        try:
            automation.start()
        except KeyboardInterrupt:
            automation.stop()

if __name__ == '__main__':
    multiprocessing.freeze_support()
    multiprocessing.set_start_method('spawn', force=True)
    main()
```

### Step 12 — Cleanup
- Delete root `ui.py` (after confirming `nexads/ui/config_window.py` works)
- Clean up all `__init__.py` files (keep empty or add explicit re-exports)
- Run full verification checklist

---

## Risks & Gotchas

| Risk | Mitigation |
|---|---|
| Circular imports | Strict one-way dependency graph (see above). No submodule imports `core/` |
| `self` references in moved methods | Replace with `ctx: WorkerContext` parameter |
| `config.json` / `referrers.json` path resolution | Use `pathlib` relative to `__file__`, not `os.getcwd()` |
| Two `QApplication` instances crashing PyQt5 | Ensure `QApplication` is only instantiated in root `main.py` |
| `asyncio` event loop shared across processes | Each worker calls `asyncio.new_event_loop()` — already done, preserve this |
| `multiprocessing.Lock` used with `asyncio` | Known issue (tracked in `docs/issues.md` — Bug #4). Do not fix during refactor, fix separately |
| Breaking changes mid-refactor | Use stub delegation methods on `nexAds` so each step is independently runnable |

---

## Verification Checklist

After each step:
- [ ] `python main.py` launches without `ImportError`
- [ ] `python main.py --config` opens GUI correctly

After Step 12 (full completion):
- [ ] `python -c "from nexads.core.automation import nexAds; print('ok')"` → `ok`
- [ ] `python -c "from nexads.ui.config_window import ConfigWindow; print('ok')"` → `ok`
- [ ] `python -m py_compile nexads/core/automation.py nexads/core/worker.py` → no output
- [ ] Root `main.py` is ≤ 30 lines
- [ ] Root `ui.py` is deleted
- [ ] No submodule imports root `main.py`
- [ ] `config.json` and `referrers.json` resolve correctly regardless of launch directory
- [ ] Full end-to-end session runs without errors
- [ ] Known bugs in `docs/issues.md` are unchanged (not fixed or reintroduced by refactor)
