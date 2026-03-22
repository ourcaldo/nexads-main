# Anti-Detection Gap Fixes — Implementation Plan

**Date:** 2026-03-22
**Goal:** Fix 9 identified gaps that AdSense / Google IVT systems can use to detect bot traffic.
**Status:** Planning

---

## Gap 1: Scroll uses JS `window.scrollBy()` instead of `page.mouse.wheel()` — DONE

### Risk: HIGH

### Problem
`random_scroll()` in `app/browser/activities.py` (lines 189-200) uses `page.evaluate("window.scrollBy(0, distance)")` for every scroll step. This fires a JavaScript `scroll` event but does NOT generate a real `WheelEvent` with `deltaX`, `deltaY`, `deltaMode` properties. AdSense JS running inside the page can distinguish between JS-injected scrolls and real mouse wheel scrolls by checking `event.deltaY` on `wheel` event listeners. A page that scrolls without any `wheel` events is a strong bot signal.

### Fix
Replace all `page.evaluate("window.scrollBy()")` calls with `page.mouse.wheel(0, distance)` in `random_scroll()`.

### Files to change
- `app/browser/activities.py` — `random_scroll()` function (lines 180-200)
  - Line 189-191: main scroll step — replace `page.evaluate(...)` with `page.mouse.wheel(0, current_step)`
  - Line 197-199: micro-correction step — replace `page.evaluate(...)` with `page.mouse.wheel(0, correction)`
- `app/navigation/tabs.py` — `natural_exit()` linger strategy (line 433-436)
  - Line 433-436: replace `page.evaluate("window.scrollBy()")` with `page.mouse.wheel()`

### Implementation details
- `page.mouse.wheel(delta_x, delta_y)` fires real `WheelEvent` at the browser level
- Keep the same step sizes and jitter logic — only change the scroll method
- The `wait_for_timeout` between steps stays the same
- For Camoufox (desktop), the `humanize=True` flag may add additional smoothing to wheel events
- Test: verify `WheelEvent` fires by adding a temporary `page.evaluate` listener check

### Acceptance criteria
- All scrolling in `random_scroll()` uses `page.mouse.wheel()`
- No remaining `window.scrollBy` calls in activity code (grep to verify)
- Micro-corrections also use `page.mouse.wheel()`
- `natural_exit` linger scroll also uses `page.mouse.wheel()`

---

## Gap 2: No pre-hover on ad before clicking — DONE

### Risk: HIGH

### Problem
`smart_click()` in `app/browser/click.py` moves the mouse to the ad element and clicks immediately after a 160-820ms dwell. There are no `mouseover` or `mousemove` events within the ad iframe/container before the click. AdSense monitors hover signals — a click without preceding hover events inside the ad container is suspicious. Real users hover over an ad (reading it, considering it) before deciding to click.

### Fix
Add a pre-hover phase in `smart_click()` when `is_ad_activity=True`: move mouse into the ad bounding box area, hover briefly (simulate reading the ad), then move to the final click point and click.

### Files to change
- `app/browser/click.py` — `smart_click()` function, between the `move_mouse_humanly` call (line 88) and the click (line 94)

### Implementation details
```
When is_ad_activity=True:
1. After scrolling ad into view and getting bounding box
2. Move mouse to a random point NEAR the ad (not on it) — simulates noticing the ad
3. Wait gaussian(400, 120, 200, 800)ms — "noticing" the ad
4. Move mouse INTO the ad bounding box to a first hover point (different from final click point)
5. Wait gaussian(600, 200, 300, 1400)ms — "reading" the ad content
6. Optionally (40% chance) move to a second point within the ad — simulates scanning
7. Wait gaussian(300, 100, 150, 600)ms
8. Move to final click point (existing logic)
9. Wait existing pre-click dwell
10. Click (existing logic)
```

- Use `choose_click_point()` with different seeds for each hover point
- The "near the ad" point should be within 50-150px of the ad box edge
- All movement uses existing `move_mouse_humanly()` and `set_cursor_position()`

### Acceptance criteria
- Ad clicks always have at least 1 hover point inside the ad before clicking
- Non-ad clicks (`is_ad_activity=False`) are not affected
- Total pre-click time for ads increases by ~1-3 seconds (acceptable)
- Hover points are within the ad bounding box

---

## Gap 3: Ad is clicked on first activity loop iteration — no pre-engagement — DONE

### Risk: HIGH

### Problem
In `perform_random_activity()` at `app/browser/activities.py` (lines 523-544), the ad interaction check happens at the top of every loop iteration. On the first iteration (when `ad_attempted_this_page` is not set), the ad click is attempted immediately — before any scrolling, hovering, or reading. The progression is: page loads → 3s settle → ad click. Real users would scroll through the page, read content, and only notice/click an ad after some engagement.

### Fix
Add a minimum pre-engagement requirement before ad interaction is attempted. The ad should only be attempted after at least 2-3 normal activities (scroll/hover) have been performed, or after a minimum time has passed (e.g., 15-30% of stay_time).

### Files to change
- `app/browser/activities.py` — `perform_random_activity()` function (lines 523-528)

### Implementation details
```
Add a condition to the ad attempt gate:

Before (line 524-528):
  if (is_ads_session
      and interact_with_ads_fn
      and not interaction_state.get("ad_attempted_this_page")
      and not interaction_state.get("ad_click_success")):

After:
  min_pre_engagement = random.uniform(0.15, 0.35)  # 15-35% of stay time
  time_engaged = time.time() - activity_start
  enough_engagement = time_engaged >= (stay_time * min_pre_engagement)

  if (is_ads_session
      and interact_with_ads_fn
      and not interaction_state.get("ad_attempted_this_page")
      and not interaction_state.get("ad_click_success")
      and enough_engagement):
```

- The `min_pre_engagement` ratio is drawn from a uniform distribution per page so it varies between pages
- Store the ratio in `interaction_state["ad_min_engagement_ratio"]` so it's consistent within a page but varies between pages
- This ensures 2-5 normal activities (scroll, hover) happen before any ad click attempt
- The existing phase system naturally puts activities in "arrival" and "reading" phases during this time

### Acceptance criteria
- Ad click never happens on the first loop iteration
- At least 15-35% of the stay time passes before ad click is attempted
- The minimum engagement ratio varies between pages
- Existing ad time budget (`ad_time_budget`) still respected

---

## Gap 4: Fixed 3s sleep after every navigation — DONE

### Risk: MEDIUM

### Problem
In `app/core/session.py`, there are hardcoded `await asyncio.sleep(3)` calls after social referrer navigation (line ~464) and direct URL navigation (line ~478). This creates a consistent 3-second gap between page load and first interaction. A constant delay is a timing signature that Google can detect across sessions.

### Fix
Replace fixed `asyncio.sleep(3)` with a randomized delay using `lognormal_seconds()`.

### Files to change
- `app/core/session.py` — two locations:
  - After social referrer navigation: `await asyncio.sleep(3)` → `await asyncio.sleep(lognormal_seconds(2.8, 0.5, 1.5, 5.5))`
  - After direct URL navigation: `await asyncio.sleep(3)` → `await asyncio.sleep(lognormal_seconds(2.8, 0.5, 1.5, 5.5))`

### Implementation details
- `lognormal_seconds(2.8, 0.5, 1.5, 5.5)` gives a median of ~2.8s with right-skew, range 1.5-5.5s
- `lognormal_seconds` is already imported in session.py
- Also check for any other hardcoded `asyncio.sleep(N)` with constant values in session.py and randomize them

### Acceptance criteria
- No remaining `asyncio.sleep(3)` in session.py navigation paths
- All post-navigation delays use lognormal or gaussian distributions
- Grep session.py for `asyncio.sleep(` followed by a bare number to verify

---

## Gap 5: Fixed 5s monitoring window after ad click — DONE

### Risk: MEDIUM

### Problem
In `app/ads/adsense.py` line 288, `evaluate_ad_click_outcome()` is called with `monitor_seconds=5.0` hardcoded. Every ad click gets exactly 5 seconds of monitoring before the outcome is evaluated. This consistent timing is a detectable pattern.

### Fix
Randomize the monitoring window using a bounded distribution.

### Files to change
- `app/ads/adsense.py` — `interact_with_ads()` function (line 288)

### Implementation details
```
Before:
  monitor_seconds=5.0

After:
  monitor_seconds=lognormal_seconds(4.5, 0.4, 3.0, 8.0)
```

- Import `lognormal_seconds` from `app.browser.humanization` (already available)
- Median ~4.5s, range 3-8s, right-skewed
- The outcome evaluator already handles variable monitoring durations

### Acceptance criteria
- `monitor_seconds` is no longer a constant
- Monitoring window varies between 3-8 seconds across clicks
- Outcome evaluation still functions correctly with variable timing

---

## Gap 6: Social platform visit is too brief and synthetic

### Risk: MEDIUM

### Problem
The social platform visit in `app/core/session.py` (lines 388-410) only does two `page.mouse.wheel()` scrolls with fixed delays. No mouse movement, no hovering on elements, no content interaction. A 3-4 second visit with exactly 2 scroll events looks synthetic.

### Fix
Make the social platform visit more realistic with varied activities.

### Files to change
- `app/core/session.py` — the social platform visit block (lines 388-410)

### Implementation details
```
Replace the current 2-scroll block with:
1. Page load + wait (existing)
2. Random cursor position in viewport (move mouse to random spot)
3. 1-3 scroll events with varied distances (not just 2)
4. 30% chance: hover on a random visible element
5. Brief idle with mouse jitter
6. Total time: 4-10 seconds (randomized)
```

- Use existing helpers: `move_mouse_humanly()`, `get_cursor_start()`, `set_cursor_position()`, `gaussian_ms()`
- Import these in session.py (some may need to be added)
- Keep it simple — this isn't a full activity loop, just enough to look like a quick social media browse

### Acceptance criteria
- Social platform visit has mouse movement (not just wheel events)
- Number of scroll events varies (1-3, not always 2)
- Optional hover on an element
- Total visit time varies between 4-10 seconds

---

## Gap 7: No reading pause simulation

### Risk: MEDIUM

### Problem
The activity loop in `perform_random_activity()` never pauses to simulate reading. After each activity, it waits 0.7-4.8s (`_idle_mouse_jitter`), then immediately picks the next activity. Real users stop scrolling at a section, hold still for 5-15 seconds while reading, then resume. The absence of these "reading pauses" makes the browsing pattern look like mechanical activity generation.

### Fix
Add a "read" activity to the weighted activity selection that simply holds position with idle mouse jitter for a longer duration.

### Files to change
- `app/browser/activities.py` — multiple locations:
  - `_build_weighted_activities()` (line 393): add `"read"` activity with phase weights
  - `perform_random_activity()` (line 563): add `"read"` handler in the selection block

### Implementation details
```
New "read" activity:
1. No scroll, no click, no hover
2. Hold current position for lognormal(5.0, 0.6, 2.5, 15.0) seconds
3. During hold, run _idle_mouse_jitter with slightly larger radius (5-15px instead of 2-8px)
4. Phase weights for "read":
   - arrival: 0.05 (rarely read on first impression)
   - reading: 0.35 (highest during reading phase)
   - exploration: 0.15 (less reading during exploration)
   - done: 0.10 (winding down)
```

- "read" does not need `can_scroll`, `can_hover`, or `can_click` capabilities — it always works
- It does NOT need to be added to `config["browser"]["activities"]` — it's an implicit behavior
- Consider making it not configurable (always enabled) since it's fundamental to looking human

### Acceptance criteria
- "read" pauses appear between other activities
- Pause duration is 2.5-15 seconds (log-normal distributed)
- Mouse has small jitter during read pauses (not frozen)
- Read pauses are most frequent during the "reading" phase

---

## Gap 8: No interaction on ad landing page after clicking

### Risk: MEDIUM

### Problem
After an ad click, `evaluate_ad_click_outcome()` waits exactly 5 seconds doing nothing on the landing page. No scroll, no mouse movement, no interaction. AdSense tracks post-click engagement — 5 seconds of zero activity on the landing page signals a non-engaged click. The `process_ads_tabs` function later dwells on ad tabs, but between the click and when `process_ads_tabs` runs, there is dead time.

### Fix
Add lightweight activity during the outcome monitoring window and in the immediate post-click phase.

### Files to change
- `app/ads/adsense.py` — `interact_with_ads()` function, after the `evaluate_ad_click_outcome` call (around line 290-310)
- `app/ads/outcomes.py` — `evaluate_ad_click_outcome()`, during the monitoring sleep

### Implementation details
```
Option A (simpler): After evaluate_ad_click_outcome returns, add a brief
activity burst on the current page (or new tab if popup opened):
1. Wait 1-2s for page to settle
2. Scroll down once (page.mouse.wheel)
3. Move mouse to a random point
4. Wait 2-4s

Option B (better but more complex): During the monitoring window in
evaluate_ad_click_outcome, instead of a passive sleep, do lightweight
activity:
1. Split monitor_seconds into 2-3 intervals
2. Between intervals, do a small mouse movement or scroll
3. Still check for navigation events between intervals
```

- Option A is recommended for simplicity — it runs after outcome evaluation
- The outcome evaluation itself should remain passive (monitoring navigation events)
- Post-click activity happens on whatever page is active after the click

### Acceptance criteria
- At least 1 scroll and 1 mouse movement happen within 10 seconds of ad click
- Outcome evaluation accuracy is not affected
- Post-click activity works for both same-tab and new-tab ad navigations

---

## Gap 9: Cursor always starts at viewport center

### Risk: LOW-MEDIUM

### Problem
`get_cursor_start()` in `app/browser/humanization.py` (lines 43-55) defaults to exact viewport center `(width/2, height/2)` when there is no stored cursor position. Every new session starts with the cursor at the same coordinates. Google can detect this consistent starting position across sessions as a bot fingerprint.

### Fix
Randomize the initial cursor position for each session.

### Files to change
- `app/browser/humanization.py` — `get_cursor_start()` function (lines 43-55)

### Implementation details
```
Before:
  viewport = page.viewport_size or {"width": 1280, "height": 720}
  return float(viewport["width"] / 2), float(viewport["height"] / 2)

After:
  viewport = page.viewport_size or {"width": 1280, "height": 720}
  w, h = viewport["width"], viewport["height"]
  # Random position in the central 60% of the viewport
  x = random.uniform(w * 0.2, w * 0.8)
  y = random.uniform(h * 0.2, h * 0.8)
  return float(x), float(y)
```

- `import random` is needed at the top of humanization.py (already imported)
- The central 60% avoids edges where a cursor would be unusual
- Each session gets a unique starting position
- The stored position still takes precedence for subsequent actions within a session

### Acceptance criteria
- Initial cursor position varies between sessions
- Position stays within the central 60% of the viewport
- Stored cursor position (from previous action) still takes priority
- No regression in cursor persistence within a session

---

## Implementation Order (recommended)

Priority based on detection risk and implementation complexity:

| Order | Gap | Risk | Effort | Files |
|-------|-----|------|--------|-------|
| 1 | Gap 1: JS scroll → mouse.wheel | HIGH | Low | activities.py, tabs.py |
| 2 | Gap 3: Pre-engagement before ad click | HIGH | Low | activities.py |
| 3 | Gap 2: Pre-hover on ads | HIGH | Medium | click.py |
| 4 | Gap 9: Random initial cursor | LOW-MED | Low | humanization.py |
| 5 | Gap 4: Randomize 3s sleep | MEDIUM | Low | session.py |
| 6 | Gap 5: Randomize 5s monitor | MEDIUM | Low | adsense.py |
| 7 | Gap 7: Reading pause activity | MEDIUM | Medium | activities.py |
| 8 | Gap 6: Better social platform visit | MEDIUM | Medium | session.py |
| 9 | Gap 8: Post-ad-click activity | MEDIUM | Medium | adsense.py, outcomes.py |

Total estimated files to modify: 7
- `app/browser/activities.py` (Gaps 1, 3, 7)
- `app/browser/click.py` (Gap 2)
- `app/browser/humanization.py` (Gap 9)
- `app/core/session.py` (Gaps 4, 6)
- `app/ads/adsense.py` (Gaps 5, 8)
- `app/ads/outcomes.py` (Gap 8)
- `app/navigation/tabs.py` (Gap 1)
