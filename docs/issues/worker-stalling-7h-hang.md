# Worker Stalling — Sessions Hanging for 6-7+ Hours

**Date:** 2026-03-20
**Commit fix:** `50038ee` — Fix worker stalling: infinite nav loop, session deadline enforcement, browser cleanup
**Affected servers:** All 10 fleet servers (nexdev, nexdev-auseast, nexdev-auscen, nexdev-nz, nexdev-my, nexdev-ausso, nexdev-austria, nexdev-bc, nexdev-bs, nexdev-swec)

## Symptom

After 3-6 hours of running, all traffic stops — no incoming users visible in analytics. But on the servers, `htop` still shows camoufox processes alive at low CPU. Workers appear running but produce no useful work.

Screenshot of the hung state: [image.png](image.png)

## Investigation (server evidence from nexdev)

### Process state after 7.5 hours of runtime

```
20 worker processes alive
16 of 20 at 0.0% CPU — completely stuck
Only 4 workers doing anything (and mostly failing)
34 total successful sessions across ALL 20 workers in 7.5 hours
```

### Log patterns found

**Pattern 1 — Infinite scroll retry loop (PRIMARY CAUSE)**

Worker 16 (and others) stuck repeating this forever with no session end:

```
Worker 16: Link click failed: ElementHandle.scroll_into_view_if_needed: Timeout 22500ms exceeded.
Worker 16: Link click failed: ElementHandle.scroll_into_view_if_needed: Timeout 22500ms exceeded.
Worker 16: Link click failed: ElementHandle.scroll_into_view_if_needed: Timeout 22500ms exceeded.
... (342 times and counting)
```

JSONL telemetry confirmed: one `url_navigation` step took **22,450,148ms (6.2 hours)**.

**Pattern 2 — networkidle timeout cascade**

Workers 3, 15 failing every session with 90s timeout:

```
Page.goto: Timeout 90000ms exceeded.
Call log:
  - navigating to "https://app.camarjaya.co.id/", waiting until "networkidle"
```

Each failed cycle: 90s timeout + 30-60s delay = ~2.5 min per attempt, zero traffic produced.

**Pattern 3 — Silent workers**

Only 12 of 20 workers ever appeared in the log. 8 workers never logged a single line — stuck before producing any output.

## Root Cause

### Bug 1: Infinite loop in `navigate_to_url_by_click` (app/navigation/urls.py)

The function has a `while retry_count < max_retries` loop (max_retries=2). Inside it:

1. A `for link in matching_links` loop tries each link on the page
2. Each link attempt is wrapped in try/except that catches `scroll_into_view_if_needed` timeout and `continue`s to next link
3. After all links fail, `random_navigation()` is called and also fails
4. **BUG:** Execution falls through to the end of the `while` body WITHOUT incrementing `retry_count`
5. `retry_count += 1` only exists in the outer `except` block (line 104), but no exception propagates because the inner loop catches them all
6. Result: **infinite loop** — the while condition never becomes false

On pages with many links (blog/insights pages), each retry cycle tries every matching link. With 50+ links at 67.5s each (22.5s timeout x 3 scroll attempts), a single cycle takes **~1 hour**. Repeated infinitely.

```python
# BEFORE (broken)
while retry_count < max_retries:
    try:
        for link, match_type in matching_links:  # 50-100 links
            try:
                await link.scroll_into_view_if_needed(timeout=22500)  # 22.5s x 3 = 67.5s per link
            except:
                continue  # catches everything, tries next link

        random_navigation()  # also fails, returns False
        # <-- FALLS THROUGH HERE, retry_count NEVER INCREMENTED
    except:
        retry_count += 1  # never reached
```

### Bug 2: `session.max_time` only checked between URL iterations

The config `session.max_time: 5` (5 minutes) was only checked at the TOP of the URL for-loop:

```python
for url_index, url_data in enumerate(ctx.config["urls"]):
    if max_time > 0 and elapsed >= max_time:  # only checked HERE
        break
    # ... navigate_to_url_by_click() hangs for 6 hours inside here
```

Once a worker entered `navigate_to_url_by_click` or the activity loop for a URL, the session deadline was never re-evaluated. A 5-minute session limit had no effect on a function stuck for hours.

### Bug 3: No browser cleanup timeout

`browser.close()` in desktop.py had no timeout. If the browser process was hung/unresponsive, the close call would wait indefinitely, leaking OS processes.

## Fixes Applied

### Fix 1: `app/navigation/urls.py` — Break the infinite loop

- Added `retry_count += 1` after the random_navigation fallthrough path — ensures the while loop always terminates
- Added `max_link_attempts_per_retry = 5` — caps how many links are tried per retry instead of iterating through all 50-100+
- Worst case: 5 links x 67.5s x 2 retries = ~11 minutes, then raises `SessionFailedException`

### Fix 2: `app/core/worker.py` — Enforce session deadline everywhere

Computed a hard `session_deadline` timestamp at session start:

```python
session_max_seconds = ctx.config["session"]["max_time"] * 60
session_deadline = session_start_time + session_max_seconds
```

Added `_session_expired()` checks at 5 points:
1. Top of URL loop (existing check, refactored)
2. Before starting activity loop — don't begin activities if time's up
3. Activity while-loop condition — exit mid-activity when deadline hits
4. Stay time calculation — cap `stay_time` to remaining session budget
5. Before ads interaction — skip ads if session is ending

### Fix 3: `app/browser/desktop.py` + `app/browser/mobile.py` — Cleanup timeouts

- `browser.close()` wrapped in `asyncio.wait_for(timeout=15)` with force-kill fallback via OS signal
- `context.close()` and `pw.stop()` wrapped in `asyncio.wait_for(timeout=10)`
- Prevents hung browser processes from blocking cleanup forever

### Fix 4: `app/core/worker.py` — Consecutive failure circuit breaker

- Tracks `consecutive_failures` counter, resets on success
- After 5 consecutive failures: kills all child browser processes via `pgrep`/`os.kill`, sleeps 120s
- On FATAL ERROR: kills child processes before exiting
- Prevents resource exhaustion from endless spawn-fail-spawn cycles

## Config Reference

```json
{
    "session": {
        "enabled": true,
        "count": 0,       // 0 = unlimited sessions
        "max_time": 5      // 5 minutes hard cap per session
    },
    "threads": 20          // 20 workers per server
}
```

- `session.max_time` is the total wall-clock limit for one session (across all 11 URLs)
- Each URL has its own `min_time`/`max_time` for per-page stay duration (separate from session limit)
- `session.count: 0` means workers loop forever (unlimited sessions)

## Files Changed

| File | Change |
|------|--------|
| `app/navigation/urls.py` | Fix infinite loop, add link attempt cap |
| `app/core/worker.py` | Session deadline enforcement, consecutive failure breaker, orphan process cleanup |
| `app/browser/desktop.py` | Timeout + force-kill on browser close |
| `app/browser/mobile.py` | Timeout on context/playwright close |
