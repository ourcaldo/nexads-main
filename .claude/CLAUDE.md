# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Context Recovery

When context is compacted or you need history from earlier in the conversation or previous sessions:
1. **claude-mem** — Use `search`, `timeline`, and `get_observations` MCP tools to find past work, decisions, and context. Always check claude-mem first before asking the user to repeat themselves.
2. **JSONL transcript** — If claude-mem doesn't have it, read the conversation transcript at `~/.claude/projects/*/[session-id].jsonl` to recover specific details.
3. **Auto-memory** — Check `~/.claude/projects/C--Users-Administrator-Desktop-nexads/memory/` for persistent notes saved across sessions.

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
    timings.py                # CENTRALIZED timing config — ALL delays/pauses defined here
    automation.py             # nexAds class: config loading, session distribution, worker orchestration
    session.py                # SessionRunner: per-worker session loop and bound helpers
    worker.py                 # WorkerContext dataclass, run_worker() multiprocessing entry
    telemetry.py              # JSONL event/heartbeat emission
  browser/
    setup.py                  # Thin orchestrator: picks desktop or mobile, delegates
    desktop.py                # Camoufox launch + cleanup
    mobile.py                 # CloakBrowser launch + cleanup (Android fingerprint via binary flags)
    activities.py             # Human-like activities: scroll, hover, click, read
    click.py                  # Smart click: curved mouse movement, pre-hover, fallback chain
    humanization.py           # Mouse movement curves, gaussian_ms/lognormal_seconds primitives
    proxy.py                  # Proxy string parsing and config resolution
    geoip.py                  # Proxy IP geolocation lookup
  ads/
    adsense.py                # AdSense detection, interaction, vignette handling
    adsterra.py               # Adsterra detection (direct DOM, iframe, external URL fallback)
    outcomes.py               # Ad click outcome tracking, classification, confidence scoring
    dispatcher.py             # Ad provider dispatch (routes to adsense/adsterra)
    signals.py                # EasyList-derived ad selector cache
  navigation/
    organic.py                # Google organic search, warm-up, cookie/consent handling
    referrer.py               # Social referrer dispatch, re-exports organic functions
    facebook.py               # Facebook referrer: fbclid generation
    instagram.py              # Instagram referrer: igshid generation
    consent.py                # Universal consent dialog detection and dismissal
    tabs.py                   # Tab management: ensure_correct_tab, process_ads_tabs, natural_exit
    urls.py                   # URL navigation: extract_domain, navigate_to_url_by_click
  ui/
    config_window.py          # PyQt5 ConfigWindow (dark mode, 3 tabs)
    config_io.py              # Config file I/O and defaults
    config_theme.py           # Dark mode styling
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

### Deploy Runner (GitHub Actions)
Manages nexads deployment across multiple GitHub accounts as Actions workflows.
Requires `tokens.txt` in repo root (format: `name:ghp_token` per line).
```bash
python scripts/deploy-runner.py init        # First time: create repos, push workflow, trigger
python scripts/deploy-runner.py redeploy    # Cancel running + re-trigger
python scripts/deploy-runner.py update      # Re-push workflow YAML + trigger
python scripts/deploy-runner.py status      # Check running workflow status
python scripts/deploy-runner.py stop        # Cancel all running workflows
# Options: -w <workers> (default 20), -m <minutes> (default 180)
```

### Testing
No test framework is configured. No tests exist. If adding tests, use `pytest`:
```bash
pip install pytest pytest-asyncio
pytest                        # Run all tests
pytest tests/test_foo.py      # Run a single test file
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

## Centralized Timing System (CRITICAL)

**All timing/delay values live in `app/core/timings.py`.** Never hardcode delays anywhere else.

### How it works
- `TIMINGS` dict maps named keys to `{"min": ms, "max": ms}` ranges
- `timing_ms(key)` returns a randomized int in milliseconds (for `page.wait_for_timeout()`)
- `timing_seconds(key)` returns a randomized float in seconds (for `asyncio.sleep()`)
- Randomization uses lognormal distribution with geometric mean of min×max, sigma=0.4

### Rules for any timing/delay changes
- **NEVER** use `random.randint()`, `random.uniform()`, `gaussian_ms()`, or hardcoded `asyncio.sleep(N)` for timing delays in any file
- **ALWAYS** use `timing_ms("key_name")` or `timing_seconds("key_name")` from `app.core.timings`
- To add a new delay: add an entry to the `TIMINGS` dict in `timings.py`, then call `timing_ms("your_key")` or `timing_seconds("your_key")`
- To change a delay value: edit the min/max in `timings.py` — the change propagates everywhere automatically
- `gaussian_ms()` and `lognormal_seconds()` in `humanization.py` are ONLY for mouse movement math and config-based stay times (url min/max, ads min/max) — not for timing delays

### Exceptions (NOT managed by timings.py)
- **Playwright operation timeouts** (`timeout=45000` in `wait_for_selector`, `goto`, etc.) — these are failure ceilings, not human-like delays
- **Per-URL stay time** (`url_data["min_time"]` / `url_data["max_time"]`) — user-configured in config.json
- **Per-ads stay time** (`config["ads"]["min_time"]` / `config["ads"]["max_time"]`) — user-configured
- **Mouse movement timing** in `humanization.py` — internal to curve generation math
- **Process monitoring** (`time.sleep(1)` in automation.py worker poll loop)

## Agent Behaviour

### Context Recovery After Compaction (MANDATORY)
- When the conversation has been compacted, ALWAYS recover the full context from the earlier conversation BEFORE continuing work.
- Use claude-mem MCP tools (`search`, `timeline`, `get_observations`) to find past decisions, findings, and context.
- If claude-mem doesn't have it, read the JSONL transcript at `~/.claude/projects/*/[session-id].jsonl` to recover specific details.
- Check auto-memory files at `~/.claude/projects/C--Users-Administrator-Desktop-nexads/memory/`.
- NEVER rely solely on the compacted summary — it loses critical details. Always verify against the original sources above.
- Do NOT ask the user to repeat information that was discussed earlier. Find it yourself.

### Git Commit Scope Rules
- Always commit and push after every change, including very small changes.
- **Before every push**, run `git status` and `git diff` to check for any user changes in the working tree. Never assume the tree is clean — the user may have made changes between your last commit and the push request.
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
- **`SessionFailedException`** is raised to abort a session early; caught in the worker loop in `SessionRunner.run()`.
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
Functions accept dependencies as callback parameters (`_fn` suffix) rather than importing directly. `SessionRunner` in `session.py` is the **composition root** -- it creates bound methods and passes them down:
```python
async def _ensure_tab_target(self, browser, page, url, wid, timeout=60):
    return await self.ensure_tab(browser, page, url, wid, timeout, "target_page_intent")
```
Follow this pattern when adding new functionality that needs access to shared state.

### Concurrency Architecture
- **`multiprocessing.Process`** for parallelism (one process per worker).
- **`asyncio`** within each worker for async browser ops.
- **`run_worker()`** bridges sync/async: creates a new event loop per process.
- Shared state via `multiprocessing.Manager()` and `multiprocessing.Lock`.
- Windows-compatible: uses `freeze_support()` and `set_start_method('spawn')`.

### Configuration
- User config in `config.json`, loaded with `json.load()`. Config is a plain `dict` passed through function parameters.
- **Timing/delay config** in `app/core/timings.py` (NOT in config.json). All delay values are centralized there.
- Use `.get(key, default)` for backward-compatible optional keys.
- Path resolution via `pathlib.Path(__file__).resolve().parent` chains.

### Browser Automation Conventions
- **Navigation:** `page.goto(url, timeout=30000, wait_until="domcontentloaded")`
- **Element queries:** `page.query_selector_all('selector')` with Playwright CSS selectors
- **Waits:** `page.wait_for_selector(selector, state="visible", timeout=45000)`
- **Delays:** `await asyncio.sleep(timing_seconds("key"))` or `await page.wait_for_timeout(timing_ms("key"))`
- **Click fallback chain:** mouse click -> native `.click()` -> JS `evaluate("el.click()")`

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
