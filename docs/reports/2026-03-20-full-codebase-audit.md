# Full Codebase Audit Report

**Date:** 2026-03-20
**Scope:** All source files in `app/`, `main.py`, `scripts/`, `config.json`
**Commit:** `582557f`

## Severity Legend

- **C** — Critical: Will cause crashes, data loss, or complete failure
- **H** — High: Significant bugs, security issues, or major performance problems
- **M** — Medium: Minor bugs, inconsistencies, or moderate performance issues
- **L** — Low: Code smell, minor style issues, or minor improvements
- **E** — Enhancement: Feature improvement or optimization opportunity

---

## Findings

### C — Critical

#### C-1: `ad_click_success` and `interaction_state` uninitialized on persistent context path
**File:** `app/core/worker.py:374`
**Description:** `ad_click_success` and `interaction_state` are initialized at line 374-375 inside the `else` (Camoufox desktop) branch. On the persistent context path (CloakBrowser mobile, lines 358-368), these variables are never set. But they're referenced later at line 741 (`if is_ads_session and not ad_click_success`) and line 717-724 (`_perform_activity(..., interaction_state)`).
**Impact:** If a mobile session is an ads session, `ad_click_success` throws `UnboundLocalError` and crashes the session. `interaction_state` causes the same error in the activity loop.
**Fix:** Move `ad_click_success = False` and `interaction_state = {"cursor_position": None}` before the `if is_persistent_context` branch (e.g., at line 257 alongside other session variables).

#### C-2: `_perform_activity` references `url` variable from enclosing scope via closure
**File:** `app/core/worker.py:221`
**Description:** The `_perform_activity` closure captures `url` at line 221 (`url if not is_ads else None`). But `url` is only assigned inside the URL for-loop (line 403-405). If `_perform_activity` is somehow called before the for-loop assigns `url` (shouldn't happen in normal flow but fragile), it would crash with `UnboundLocalError`.
**Impact:** Low probability but the closure binding is fragile. Any refactor that calls `_perform_activity` outside the URL loop will crash.
**Fix:** Pass `url` as an explicit parameter to `_perform_activity` instead of capturing it from the outer scope.

---

### H — High

#### H-1: Race condition on `pending_ads_sessions` shared counter
**File:** `app/core/worker.py:242-244`
**Description:** The read-decrement pattern on `ctx.pending_ads_sessions.value` is not atomic:
```python
if ctx.pending_ads_sessions.value > 0:   # read
    ctx.pending_ads_sessions.value -= 1  # decrement
```
Multiple worker processes can read `value > 0` simultaneously, all decrement, and over-allocate ads sessions beyond the CTR budget.
**Impact:** Actual CTR will exceed configured target. With 20 workers, the first batch of sessions could all become ads sessions.
**Fix:** Use a `multiprocessing.Lock` around the read-decrement, or use `multiprocessing.Value` with its built-in lock:
```python
with ctx.pending_ads_sessions.get_lock():
    if ctx.pending_ads_sessions.value > 0:
        ctx.pending_ads_sessions.value -= 1
        is_ads_session = True
```

#### H-2: Ads session budget never replenished in unlimited mode
**File:** `app/core/automation.py:110-111`
**Description:** In unlimited session mode (`session.count == 0`), `ads_sessions` is set to `max(1, int(100 * (ctr / 100)))`. With `ctr=20`, that's 20 ads sessions total. Once all 20 are consumed by workers, `pending_ads_sessions.value` stays at 0 forever — no more ads sessions are ever created.
**Impact:** After the first ~20 sessions, CTR drops to 0% permanently. All remaining sessions are normal-only.
**Fix:** Replenish the ads budget periodically, or implement a per-worker probability-based approach instead of a global counter.

#### H-3: `_session_remaining` and `_session_expired` closures capture `session_deadline` by reference but it's reassigned each loop iteration
**File:** `app/core/worker.py:263-270`
**Description:** `_session_remaining()` and `_session_expired()` are defined inside the `while ctx.running` loop and close over `session_deadline`. Since `session_deadline` is reassigned at the top of each iteration (line 261), and these functions are defined inside the same scope, they always see the latest value. This works correctly in Python — but they're re-created every iteration, which is wasteful.
**Impact:** No bug, but unnecessary function object creation 20x per session. Very minor.
**Fix:** (L priority) — could be refactored but not worth changing.

#### H-4: JSONL telemetry writes are not process-safe
**File:** `app/core/telemetry.py:35-36`
**Description:** `_append_jsonl` opens the file and writes without any locking. With 20 worker processes writing simultaneously, JSONL lines can interleave and produce corrupt JSON.
**Impact:** Telemetry files may contain corrupted lines that break log analysis.
**Fix:** Use `fcntl.flock()` on Linux or a `multiprocessing.Lock` for process-safe writes.

---

### M — Medium

#### M-1: `redirect_budget_states` accumulates entries forever
**File:** `app/core/worker.py:109`
**Description:** `redirect_budget_states` dict grows with every unique `intent_type:url` key across all sessions. It's never cleared between sessions.
**Impact:** Memory grows linearly with number of unique URLs visited. With unlimited sessions, this dict grows indefinitely. In practice the URL list is small (11 URLs), so this is bounded.
**Fix:** Clear `redirect_budget_states` at the start of each session iteration.

#### M-2: `_random_nav` closure defined inside `else` branch but used in URL loop
**File:** `app/core/worker.py:378-388`
**Description:** `_random_nav` is defined at line 378 inside the `else` (desktop) branch. On the persistent context path (mobile), it's never defined. But `navigate_to_url_by_click` at line 513 passes `_random_nav` — if device is mobile, this would throw `UnboundLocalError`.
**Impact:** Mobile sessions that reach subsequent URL navigation (url_index > 0) will crash.
**Fix:** Move `_random_nav` definition before the `if is_persistent_context` branch.

#### M-3: `random_navigation` function has same retry_count bug pattern (partially)
**File:** `app/navigation/urls.py:183-197`
**Description:** In `random_navigation`, when `smart_click_fn` returns False (click didn't work), execution falls through without incrementing `retry_count`. The click returning False means the function never enters the `if page.url != original_url` check, and falls to the end of the try block without incrementing.
**Impact:** Not infinite (the `for attempt in range(3)` scroll loop will eventually raise on scroll failure), but could cause extra unnecessary iterations.
**Fix:** Add `retry_count += 1` after the `if await smart_click_fn(...)` block when click returns False.

#### M-4: `perform_organic_search` doesn't clean up interceptor on early returns
**File:** `app/navigation/referrer.py:128-130`
**Description:** If `search_input` is None (line 128-130), the function returns False without calling `page.unroute()`. The request interceptor that blocks `accounts.google.com` remains active for the rest of the session.
**Impact:** Google account-related requests blocked for entire session. Unlikely to cause visible issues but technically leaks a route handler.
**Fix:** Use try/finally to ensure `page.unroute()` is always called.

#### M-5: `_CLOAKBROWSER_DIRS` dict is process-global but workers are separate processes
**File:** `app/browser/mobile.py:37`
**Description:** `_CLOAKBROWSER_DIRS` is a module-level dict. Since workers run in separate processes (multiprocessing), each process gets its own copy. This works correctly — but if the architecture ever changes to threads, this would break.
**Impact:** No current bug. Correct for multiprocessing but fragile assumption.
**Fix:** Document the assumption with a comment.

---

### L — Low

#### L-1: Unused import `Any` in worker.py
**File:** `app/core/worker.py:12`
**Description:** `from typing import Any` is imported but never used.
**Fix:** Remove the import.

#### L-2: `RateLimiter` class is defined but never used
**File:** `app/core/automation.py:25-51`
**Description:** `RateLimiter` is instantiated at line 67 (`self.rate_limiter = RateLimiter()`) but `wait_if_needed()` is never called anywhere in the codebase.
**Impact:** Dead code.
**Fix:** Remove if not planned for future use. Already noted in AGENTS.md Known Issues.

#### L-3: `get_random_delay` in automation.py duplicates `get_delay` in worker.py
**File:** `app/core/automation.py:113-117`
**Description:** `nexAds.get_random_delay()` uses `random.randint` while the worker's `get_delay()` uses `lognormal_seconds` for more natural timing. The automation.py version is never called.
**Impact:** Dead code.
**Fix:** Remove if unused.

#### L-4: Debug print statement left in production code
**File:** `app/navigation/referrer.py:103`
**Description:** `print(f"DEBUG - Raw keyword data: {repr(keywords)}")` — debug output in production.
**Fix:** Remove the debug print.

#### L-5: `_kill_child_browser_processes` uses `pgrep`/`pkill` which don't exist on Windows
**File:** `app/core/worker.py:60-86`
**Description:** The function calls `pgrep` and `pkill` which are Linux-only. On Windows dev machines, both the primary and fallback paths silently fail.
**Impact:** No impact in production (Linux servers). Development testing won't clean up orphans.
**Fix:** Acceptable as-is since production is Linux-only. Could add a platform check.

#### L-6: Fragile `if "fingerprint_mode" in locals()` checks
**File:** `app/core/worker.py:949-965`
**Description:** The `emit_mobile_fingerprint_event` call uses `if "fingerprint_mode" in locals()` multiple times. This pattern is fragile — any rename or scope change breaks it silently.
**Fix:** Initialize `fingerprint_mode = "desktop"` and `fallback_reason = ""` at the top of the session block (alongside other session variables) instead of checking locals().

---

### E — Enhancement

#### E-1: Randomize mobile device profiles
**File:** `app/browser/mobile.py:16-21`
**Description:** Currently hardcoded to Google Pixel 8 (Android 14). Every mobile session uses identical UA, viewport, and GPU.
**Suggestion:** Create a pool of 5-10 mobile profiles (Pixel 8, Pixel 7, Samsung Galaxy S24, etc.) with matching UA/viewport/GPU/DPR and randomly select one per session. This makes mobile traffic less fingerprintable.

#### E-2: Add session.min_time config option
**File:** `app/core/worker.py:260`
**Description:** Currently only `session.max_time` exists. Sessions that complete all URLs quickly end in <1 minute, which looks unnatural.
**Suggestion:** Add `session.min_time` to enforce a minimum session duration (pad with extra activity time if needed).

#### E-3: Rotate proxy per session instead of per worker
**File:** `app/browser/setup.py:17`
**Description:** `resolve_proxy_config()` is called once per session, picking a random proxy from the file. This is correct. But the proxy is not sticky across the session — if the browser reconnects, it might get a different proxy.
**Suggestion:** This already works well. No change needed.

#### E-4: Add health monitoring endpoint or file
**Description:** Workers have no way to report health externally. The only signal is log output.
**Suggestion:** Write a periodic heartbeat file (e.g., `data/worker_heartbeats.json`) with last-active timestamp per worker. The fleet script could check this to detect stuck workers without parsing logs.

#### E-5: JSONL log rotation
**File:** `app/core/telemetry.py`
**Description:** JSONL files grow unbounded. On long-running servers, `worker_events.jsonl` can grow to hundreds of MB.
**Suggestion:** Rotate by date or size. Or truncate on deploy (the deploy script already runs `git clean -fd` which removes data files).

#### E-6: Reduce `networkidle` timeout from 90s to 30-45s
**File:** Multiple locations in `worker.py`
**Description:** `page.goto(url, timeout=90000, wait_until="networkidle")` waits up to 90 seconds. Many sites never reach `networkidle` due to analytics/tracking scripts that keep firing.
**Suggestion:** Reduce to 30-45s or use `wait_until="domcontentloaded"` with a shorter timeout, then optionally wait for `networkidle` with a secondary timeout. This prevents 90s wasted on each failed navigation.

---

## Summary

| Severity | Count | Action Required |
|----------|-------|-----------------|
| **C** (Critical) | 2 | Fix before next deploy |
| **H** (High) | 4 | Fix soon |
| **M** (Medium) | 5 | Fix when convenient |
| **L** (Low) | 6 | Low priority |
| **E** (Enhancement) | 6 | Future improvements |
| **Total** | 23 | |

### Immediate Action Items (C + H) — ALL FIXED

1. **C-1**: FIXED — Moved `ad_click_success` and `interaction_state` before persistent context branch
2. **C-2**: FIXED — Added explicit `target_url` parameter to `_perform_activity`
3. **M-2**: FIXED — Moved `_random_nav` before persistent context branch (same fix as C-1)
4. **H-1**: FIXED — Replaced shared counter with per-session probability (`random.random() * 100 < ctr`)
5. **H-2**: FIXED — Same fix as H-1. Per-session probability never exhausts, works forever in unlimited mode
6. **H-4**: FIXED — Added `fcntl.flock()` file locking for process-safe JSONL writes (with Windows fallback)
