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
python3 -m cloakbrowser install
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

### Dual-Browser Architecture (Critical)

Camoufox does NOT support mobile device emulation. The project uses two separate browser engines:

- **Desktop sessions**: Camoufox (anti-detect Firefox) — handles fingerprinting, geoip, humanization at engine level
- **Mobile sessions**: CloakBrowser (stealth Chromium) — custom Chromium binary with 33 source-level C++ fingerprint patches

#### CloakBrowser (Mobile Engine)
- **What it is**: Custom-compiled Chromium binary with fingerprints modified at the C++ source level. Not JS injection or CDP config — real source patches. Drop-in Playwright replacement.
- **Import**: `from cloakbrowser import launch_persistent_context_async`
- **Install**: `pip install cloakbrowser[geoip]` then `python3 -m cloakbrowser install` (downloads ~200MB binary)
- **Key advantage over Patchright**: Source-level patches affect ALL contexts including Web Workers. No `hasInconsistentWorkerValues` mismatch. Bot detection: **No Detection** on BrowserScan.
- **Fingerprint management**: Binary auto-generates coherent fingerprint from a seed (`--fingerprint=<int>`). Canvas, WebGL, audio, fonts, GPU, screen all derived from same seed.
- **GeoIP**: Built-in `geoip=True` parameter auto-detects timezone/locale from proxy IP.
- **Persistent context**: `launch_persistent_context_async()` avoids incognito detection.

#### CloakBrowser Mobile Flags
```
--fingerprint=<random seed>                     # Unique identity per session
--fingerprint-platform=android                  # Navigator.platform, UA OS
--fingerprint-gpu-vendor=Qualcomm               # WebGL vendor (mobile GPU)
--fingerprint-gpu-renderer=ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)
--fingerprint-screen-width=412                  # Mobile screen
--fingerprint-screen-height=915
--fingerprint-storage-quota=5000                # Bypass incognito detection
--fingerprint-hardware-concurrency=8
--fingerprint-device-memory=8
```

#### CloakBrowser Known Limitations
- **Audio exception (-5%)**: Binary-level audio patch flagged by BrowserScan. Cannot fix from our side.
- **DNS leak (-3%)**: HTTP proxies don't tunnel DNS. Only SOCKS5 fixes this.
- **Incognito detection (-10%)**: `--fingerprint-storage-quota=5000` mitigates but may not fully resolve on all Xvfb configurations.
- **`navigator.platform` on Linux**: `--fingerprint-platform=android` may show `Linux x86_64` instead of `Linux armv8l` on x86 servers. Does not affect bot detection.
- **Best achievable score**: ~67-77% on BrowserScan with HTTP proxy. Bot Detection: **No Detection** (the metric that matters).

#### Key Architectural Rule
- Never use raw `playwright` or `playwright-stealth` for any browser session. Desktop uses Camoufox. Mobile uses CloakBrowser.
- BrowserForge is only used by Camoufox for `Screen` constraints. CloakBrowser handles its own fingerprinting at binary level.

#### Browser Module Structure
```
app/browser/
  setup.py          # Thin orchestrator: picks desktop or mobile, delegates
  proxy.py          # Proxy string parsing and config resolution (shared)
  desktop.py        # Camoufox launch + cleanup
  mobile.py         # CloakBrowser launch + cleanup (Android fingerprint via binary flags)
  activities.py     # Human-like scroll, hover, click
  humanization.py   # Mouse movement, timing helpers
  geoip.py          # Proxy IP geolocation lookup (used by proxy.py for URL building)
```

### Known Issues / Tech Debt
- None currently tracked.
