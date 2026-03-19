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
python -m playwright install firefox
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

Commit and push workflow policy is maintained in `.github/copilot-instructions.md`.

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

### Known Issues / Tech Debt
- `SessionFailedException` is defined in both `automation.py` and `worker.py` (duplicate).
- No `.gitignore` -- `__pycache__/`, `.vscode/`, proxy credentials may be tracked.
- Several dependencies in `requirements.txt` appear unused: `selenium`, `undetected-chromedriver`, `keyboard`, `pynput`, `humanize`.
