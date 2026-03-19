## Implementation Tracker

| Section | Area | Status | Notes |
|---|---|---|---|
| 14 | Ad Outcome Validation Pipeline | Implemented | Outcome scoring/classification, normalized payload, and per-attempt JSONL persistence are active. |
| 15 | Multi-Network Ad Detection (Beyond AdSense) | Not Started | Runtime is still primarily AdSense/Google-family focused. |
| 16 | GDPR Consent Failure: Click Interception Handling | Implemented | Universal consent handling and interception-aware fallback flow are active. |
| 17 | Redirect-Resilient Navigation Guard | Implemented | NavigationIntent, intent-aware matching, reason codes, and per-intent redirect budgets are active. |
| 18 | Same-Tab Ad Landing Handling (Keep It Simple) | Implemented | Same-tab/new-tab detection is automatic, and same-tab dwell uses existing ads min/max settings without new config keys. |
| 19 | Step-Level Crash and Failure Telemetry | Implemented | Step-level JSONL telemetry is active in data/worker_events.jsonl and mirrored failures in data/worker_errors.jsonl. |
| 20 | Prioritized Next Sprint Checklist | In Progress | Several prerequisites are in place, but checklist deliverables are not fully complete yet. |

Status legend: `Not Started`, `In Progress`, `Implemented`.

## 14. Ad Outcome Validation Pipeline

### Why this is needed

Current ad interaction mostly relies on selector matching plus did a new tab open.
That can misclassify outcomes:
- Some ad clicks navigate in the same tab.
- Some clicks open popups/interstitials that are not real ad landings.
- Some pages trigger redirects after delay, so immediate checks miss real outcomes.

Goal: move from binary heuristics to a scored validation pipeline for every ad click attempt.

### 14.1 New-tab or same-tab outcome detection

What it is:
- Determine whether a click resulted in:
  - new_tab_navigation
  - same_tab_navigation
  - no_navigation

How it works:
1. Capture baseline before click:
- current page URL
- current tab IDs
- timestamp
2. Execute click with expect_popup guard and same-tab watcher.
3. For 2-5 seconds post-click, poll:
- context pages count
- active page URL changes
- load state transitions
4. Return a normalized outcome object.

What it is for:
- Prevent false negatives where same-tab ad nav is incorrectly treated as failed.
- Keep metrics accurate for ad interaction success.

### 14.2 Redirect chain capture

What it is:
- Record URL transition chain from click start to final landing.

How it works:
1. Attach lightweight event hooks around click window:
- framenavigated (top frame only)
- optional response hooks for redirect status (3xx)
2. Store ordered transitions:
- [initial_url, redirect_1, redirect_2, ..., final_url]
3. Stop capture when:
- networkidle is reached and URL stable for N ms, or
- timeout reached (for example, 8-12s).

What it is for:
- Distinguish real ad delivery paths from script noise.
- Build reliable destination-domain evidence.
- Improve debugging when outcomes look inconsistent.

### 14.3 Destination-domain classification

What it is:
- Classify final navigation target as one of:
  - ad_destination
  - same_site_internal
  - uncertain
  - blocked_or_failed

How it works:
1. Compare final domain vs source domain.
2. Evaluate redirect-chain patterns:
- known ad-serving hosts/signatures (maintained list)
- known tracking/redirect hubs
3. Evaluate path/query signals:
- ad click IDs, campaign params, tracking params
4. Assign category + reason codes.

What it is for:
- Reduce misclassification where random internal click is counted as ad success.
- Produce cleaner analytics and safer retry decisions.

### 14.4 Confidence score per click event

What it is:
- A numeric score (0.0-1.0) estimating confidence that the click was a valid ad interaction outcome.

How it works:
1. Compute weighted signals, for example:
- +0.25 popup/new-tab detected
- +0.25 URL changed away from source domain
- +0.20 redirect chain includes ad/tracker signatures
- +0.15 landing remains stable greater than N seconds
- +0.15 successful load state/network activity pattern
2. Subtract for contradictions, for example:
- -0.30 immediate bounce to original page
- -0.20 no meaningful URL change
- -0.20 blocked/error outcomes
3. Clamp to [0, 1], persist score with event metadata.

What it is for:
- Replace brittle true/false checks with robust graded outcomes.
- Enable threshold-based policy (for example, success if score >= 0.6).
- Improve model tuning over time using real logs.

### Data model extension

For each ad click attempt, store:
- click_id
- source_url
- source_domain
- outcome_type (new_tab_navigation / same_tab_navigation / no_navigation)
- redirect_chain (ordered list)
- final_url
- final_domain
- classification
- confidence_score
- reason_codes
- timings_ms

### Acceptance criteria

1. Same-tab ad navigations are detected and counted correctly.
2. Redirect chains are captured for successful click attempts.
3. Each attempt has destination classification + confidence score.
4. Legacy binary success metric remains available for backward compatibility.
5. Logs show concise outcome summary per ad click attempt.

### Implementation priority

1. New-tab/same-tab outcome detection
2. Redirect chain capture
3. Domain classification
4. Confidence scoring

---

## 15. Multi-Network Ad Detection (Beyond AdSense)

### Why this is needed

Current runtime detection is strongest for AdSense/Google-family patterns.
Many target pages use non-Google ad systems (native widgets, direct ad servers, affiliate overlays).
Without broader classification, interaction quality and metrics are biased toward one ad family.

### Objective

Add a network-family detection layer that classifies ad candidates as:
- google_adsense_family
- native_recommendation_widget
- direct_ad_iframe_or_script
- affiliate_or_popunder_overlay
- uncertain_ad_candidate

### Implementation approach

1. Extend signal extraction keywords and outputs:
- generate per-family host/selector buckets in data files.
2. Introduce family-aware detection in ad interaction logic:
- score candidates using selector match + host/path signatures.
3. Keep backward compatibility:
- existing AdSense pathway remains active.
4. Expose family in click outcomes:
- include detected ad_family in logs/metrics.

### Acceptance criteria

1. Non-Google ad candidates can be detected and labeled.
2. Click outcomes are tracked by ad_family.
3. Existing AdSense success flow remains unchanged for Google-family matches.

---

## 16. GDPR Consent Failure: Click Interception Handling

### Observed case

Consent button click can be intercepted by an overlay anchor and time out.
After failure, the worker may continue random activity while consent remains visible.

### Root cause

1. Pointer interception:
- another element sits above the consent target and receives click events.
2. Handler behavior:
- consent handling can return unresolved while caller continues session flow.

### Objective

Make consent handling resilient and stateful:
- detect interception,
- recover with alternative click paths,
- gate main activity until consent is resolved or explicitly skipped by policy.

### Implementation approach

1. Interception-aware fallback chain:
- native click attempt,
- mouse click at computed center,
- JS evaluate click,
- optional force-click mode for consent selectors only.
2. Overlay mitigation:
- detect intercepting element via elementFromPoint,
- dismiss/close known overlay patterns when safe.
3. Consent gating policy:
- if consent unresolved, retry for bounded attempts/time window,
- pause random activities during retry window,
- mark page as consent_unresolved if retries exhausted.
4. Structured outcome state:
- consent_status: resolved | unresolved | skipped
- include reason_code (timeout, intercepted, selector_not_found, and so on).

### Acceptance criteria

1. Intercepted consent targets are retried with fallback click strategies.
2. Main activity does not immediately continue while consent retries are active.
3. Final consent outcome is logged with reason code.
4. Session behavior is deterministic when consent cannot be resolved.

---

## 17. Redirect-Resilient Navigation Guard

### Why this is needed

Fast redirects, aborts (NS_BINDING_ABORTED), and same-tab ad landings still create brittle outcomes if recovery is only URL-based.
Need a deterministic guard that understands intent and state, not just the latest URL.

### Objective

Build a small navigation state machine that tracks expected destination intent per step:
- target_page_intent
- ad_landing_intent
- recovery_intent

### Implementation approach

1. Introduce a NavigationIntent object containing:
- expected_domain
- allowed_domain_suffixes
- intent_type
- created_at
- max_recovery_seconds
2. Pass intent into ensure_correct_tab so recovery policy differs by step.
3. Add redirect_budget counters:
- max recoveries per URL
- max new tabs spawned per URL
4. If budget is exceeded:
- mark URL step as failed with reason code,
- continue session or abort based on policy.

### Acceptance criteria

1. Recovery behavior differs correctly between target browsing and ad landing contexts.
2. Redirect loops are terminated deterministically with explicit reason codes.
3. Workers do not fail immediately on single transient aborts.

---

## 18. Same-Tab Ad Landing Handling (Keep It Simple)

### Why this is needed

Same-tab ad landings are common, and should be handled automatically without introducing unnecessary config complexity.

### Objective

Keep detection and dwell policy simple:
- detect same-tab vs new-tab outcomes from runtime behavior,
- reuse existing `ads.min_time` and `ads.max_time` for ad dwell,
- avoid adding separate same-tab config unless proven necessary.

### Implementation approach

1. Detect navigation outcome from tab/page state after ad click.
2. For same-tab ad landings, calculate dwell time from existing `ads.min_time` and `ads.max_time`.
3. Return to target URL using current recovery guard path and keep existing logs.
4. Defer extra same-tab-specific config unless recurring real-world failures justify it.

### Acceptance criteria

1. Same-tab/new-tab outcomes are auto-detected reliably.
2. Same-tab ad dwell uses existing ads min/max settings (no hardcoded override window).
3. Return path success/failure remains visible in logs.
4. No extra same-tab config keys are required for normal operation.

---

## 19. Step-Level Crash and Failure Telemetry

### Why this is needed

Process-level traceback can be hard to map to a specific lifecycle step.
Need structured diagnostics to identify exact failure phase quickly.

### Objective

Emit a lightweight structured event record for every major worker step.

Runtime outputs:
- `data/worker_events.jsonl` for all emitted step events.
- `data/worker_errors.jsonl` for failure-only mirrored events.

### Implementation approach

1. Add emit_worker_event helper (JSON line print or file sink) with:
- worker_id
- session_id
- url_index
- step_name
- status
- url
- domain
- error_type
- error_message
- timestamp
2. Instrument steps:
- initial goto
- ensure tab
- cookies
- consent
- vignette
- activity loop
- ad click
- same-tab return
3. On exception, include compact traceback tail (single line summary).

### Acceptance criteria

1. Every failed session has a clear final failed step.
2. Operators can identify top recurring failure reasons from logs alone.
3. Existing print logs remain, with structured events added in parallel.

---

## 20. Prioritized Next Sprint Checklist

1. P0: Keep same-tab handling simple and aligned with existing ads min/max (Section 18). Completed.
2. P0: Step-level telemetry with failure reason codes (Section 19). Completed.
3. P1: Intent-aware redirect guard and redirect budgets (Section 17).
4. P1: Add session-end counters:
- redirect_recoveries
- same_tab_ad_returns
- consent_unresolved_count.
5. P2: Persist daily metrics snapshot to data/session_metrics.json for quick health checks.
