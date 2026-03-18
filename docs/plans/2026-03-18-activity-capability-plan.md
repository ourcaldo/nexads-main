# Enhancement Plan: Capability-Aware Random Activity Selection

Date: 2026-03-18
Scope: Prevent repeated impossible actions (starting with non-scrollable pages)
Priority: High

## Problem

Current behavior can repeatedly choose an activity that is not possible on the current page.
Example observed:
- Activity selected: scroll
- Runtime result: "Page is not scrollable"
- Selection repeats again and again within the same stay window

This reduces realism and wastes the activity budget for the session.

## Goal

Before performing an activity, detect whether each activity is currently feasible and only choose from feasible options.
If an activity has already failed due to an unchanging page capability, temporarily suppress it for the same page/session.

## Functional Requirements

1. Build an activity capability check layer for each page state:
- `can_scroll`
- `can_hover`
- `can_click`

2. Random activity selector must only sample from currently feasible activities.

3. If all activities are infeasible:
- Wait a short randomized delay
- Re-evaluate capabilities
- Avoid tight retry loops

4. If `scroll` is determined not feasible on a page:
- Mark it as blocked for that page context
- Do not attempt `scroll` again until a page-state change event occurs

5. Page-state change should reset or re-evaluate capability cache:
- URL change
- major DOM/height change
- navigation to a new tab/page

## Proposed Implementation

## 1) Add capability snapshot helper

Add helper in activity layer (or humanization/activity module):
- `get_activity_capabilities(page) -> dict[str, bool]`

Suggested checks:
- `can_scroll`: `document.documentElement.scrollHeight > (window.innerHeight + threshold)`
- `can_hover`: there are visible hoverable targets (`a`, `button`, `[role="button"]`, etc.)
- `can_click`: there are visible clickable targets in viewport or page

## 2) Add activity suppression cache in interaction state

Extend existing `interaction_state` with page-scoped suppression, e.g.:
- `blocked_activities_by_url`
- `last_capability_snapshot`

Rules:
- If `scroll` fails with non-scrollable signal, block `scroll` for current URL
- Unblock when URL changes or capability snapshot changes to `can_scroll=True`

## 3) Update random activity selector

Current logic selects from configured activities directly.
Change to:
1. Start from configured list
2. Remove activities not currently feasible
3. Remove page-blocked activities
4. Randomly pick from remaining list
5. If none remain, short idle delay and re-check

## 4) Add bounded retry/backoff

When no activities are possible:
- Sleep using bounded random/lognormal delay (e.g. 0.6s-2.2s)
- Retry capability check
- Max consecutive no-op loops before skipping to next phase

## 5) Improve diagnostics

Replace repeated logs:
- from repeated: "Page is not scrollable"
- to structured once-per-state logs:
  - "Activity capability: scroll=false, hover=true, click=true"
  - "Blocked activity scroll for current URL (not scrollable)"

## Acceptance Criteria

1. On a non-scrollable page, script should not repeatedly attempt scroll in the same page state.
2. With all activities enabled, selector chooses only feasible actions.
3. After navigation to a different page, previously blocked activities are re-evaluated.
4. Logs show capability filtering decisions clearly and without spam.
5. No regression in normal pages where scrolling is available.

## Test Plan

1. Non-scrollable static page:
- Confirm at most one scroll-failure signal per page state
- Confirm subsequent activity picks are hover/click/idle (not repeated scroll)

2. Scrollable article page:
- Confirm scroll remains selectable and executes normally

3. Dynamic page that becomes scrollable later:
- Confirm scroll can be re-enabled after capability re-check

4. Multi-URL session:
- Confirm blocked activity cache resets/re-evaluates on URL change

## Rollout Notes

1. Implement under existing random activity flow first.
2. Keep behavior backward compatible with current config schema.
3. Optional future config toggle:
- `browser.capability_filtering: true` (default true once validated)
