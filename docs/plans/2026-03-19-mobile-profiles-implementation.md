# Mobile Fingerprint Integration Plan
Date: 2026-03-19

## Goal
Build a maintainable mobile fingerprint integration path that uses BrowserForge generation and Playwright context mapping, while keeping behavior consistent, measurable, and operationally safe in the current codebase. Along side with:
1. Make sure that the fingerprint is consistent
2. Undetectable + stealth and user mimicking

## Mandatory Constraints
1. Mobile constraints are hardcoded in code for this milestone.
2. Do not add any new runtime keys in config.json for this feature path.
3. Persistent browser storage remains disabled for this feature path.
4. Every worker must receive a fresh fingerprint session identity per worker session.
5. Desktop behavior remains unchanged unless mobile branch is explicitly enabled in code.

## Baseline Integration Points
1. Browser launch setup: app/browser/setup.py
2. Worker session orchestration: app/core/worker.py
3. Telemetry stream: app/core/telemetry.py
4. Runtime config (read-only for this feature): config.json

## Working Definitions
1. Fresh fingerprint session identity means a newly generated fingerprint used once for one worker session/context.
2. Dry-run means generation, mapping, and validation execute but mobile context is not activated.
3. Fallback means immediate return to stable desktop flow when preflight checks fail.

## Implementation Plan (Detailed)

### Step 1: Define Acceptance Gates and Stop Conditions
Goal: avoid scope drift and keep execution decisions objective.
Tasks:
1. Write clear acceptance gates for crash rate, fallback rate, and validation errors.
2. Define stop conditions that force fallback-only mode.
3. Define rollback criteria and owners.
Output:
1. Acceptance table embedded in this plan.
2. Go or no-go checklist for rollout stages.
Completion Criteria:
1. Team can answer what success looks like before code changes start.
2. Team can answer exactly when rollout must be halted.

### Step 2: Document Current Desktop Flow Before Touching Code
Goal: isolate integration points and reduce regression risk.
Tasks:
1. Trace call path from worker startup to browser/context creation.
2. Mark points where mobile fingerprint generation can be inserted.
3. Mark points where fallback returns to desktop path safely.
Output:
1. Current-state flow map and insertion points.
Completion Criteria:
1. Integration points are identified in setup.py and worker.py.
2. No uncertain insertion point remains.

### Step 3: Add In-Code Strategy Constants (No New Config)
Goal: control behavior without increasing config complexity.
Tasks:
1. Define hardcoded strategy constants near browser setup code.
2. Define hardcoded mobile constraints in one place.
3. Define hardcoded retry and fallback limits.
Output:
1. Constants block in setup layer with concise comments.
Required Hardcoded Defaults:
1. Device: mobile
2. Screen bounds: min_width=360, max_width=430, min_height=740, max_height=932
3. Retry attempts: 1 regeneration max
4. Fallback: desktop path on any preflight failure
Completion Criteria:
1. No new keys added to config.json.
2. All mobile constraints readable in one code block.

### Step 4: Build Fingerprint Generation Layer
Goal: generate one full fingerprint session identity per worker session.
Tasks:
1. Create generation routine that receives worker context and hardcoded constraints.
2. Generate BrowserForge fingerprint using browser, os, device, and screen bounds.
3. Produce a normalized summary object for telemetry.
4. Add timeout and one retry path.
Output:
1. Reusable generator function callable from setup flow.
Completion Criteria:
1. One worker session gets one newly generated fingerprint.
2. Failed generation follows retry then fallback policy exactly.

### Step 5: Implement Native Playwright Mapping Layer
Goal: apply stable and high-value fingerprint fields with low risk.
Tasks:
1. Map fingerprint navigator.userAgent to context user_agent.
2. Map fingerprint screen width and height to viewport.
3. Map device scale ratio to device_scale_factor.
4. Map language to locale and accepted language header.
5. Map mobile and touch flags consistently.
6. Filter and map safe request headers only.
Output:
1. Deterministic context mapping function in setup path.
Completion Criteria:
1. Mapping output is deterministic for same input fingerprint.
2. No unsupported or unsafe header injection.

### Step 6: Add Preflight Consistency Validator
Goal: block impossible fingerprint combinations before navigation begins.
Tasks:
1. Validate UA family against platform expectations.
2. Validate mobile flag and touch capability coherence.
3. Validate locale and language header coherence.
4. Validate viewport class is within hardcoded mobile bounds.
5. Trigger regenerate-once then fallback-on-fail behavior.
Output:
1. Validator returning pass or fail plus reason codes.
Completion Criteria:
1. Invalid combinations never reach active navigation stage.
2. Failure reasons are logged and actionable.

### Step 7: Add Optional Advanced Override Mode Behind Strict Internal Flag
Goal: keep default path maintainable while allowing controlled experiments.
Tasks:
1. Keep native mapping as default behavior.
2. Place override logic behind explicit internal false-by-default flag.
3. Track which fields were applied natively versus not applied.
Output:
1. Guarded experiment branch that is inert by default.
Completion Criteria:
1. Default production path remains native mapping only.
2. Override mode cannot activate accidentally.

### Step 8: Add Telemetry and Diagnostics
Goal: make fingerprint quality measurable and failures debuggable.
Tasks:
1. Emit per-session fingerprint summary and strategy mode.
2. Emit validation pass or fail and reason codes.
3. Emit fallback reason and target path.
4. Emit session outcome segmented by desktop versus mobile branch.
Output:
1. Structured telemetry events in telemetry.py and worker call sites.
Completion Criteria:
1. Each session has an auditable fingerprint lifecycle.
2. Metrics can be grouped by strategy stage.

### Step 9: Build Dry-Run Path
Goal: validate generation and mapping safely with no behavior change.
Tasks:
1. Run generation, mapping, and validation in dry-run branch.
2. Record all telemetry and preflight results.
3. Skip mobile activation and continue desktop execution.
Output:
1. Dry-run mode that proves readiness without traffic impact.
Completion Criteria:
1. No mobile context activation in dry-run stage.
2. Sufficient telemetry for rollout decision.

### Step 10: Execute Staged Rollout
Goal: reduce risk while collecting evidence.
Tasks:
1. Stage A: dry-run only with complete telemetry.
2. Stage B: limited mobile enablement with strict fallback.
3. Stage C: wider enablement after stability confirmation.
Output:
1. Stage checklist and pass or fail records.
Completion Criteria:
1. Each stage has explicit go or no-go result before advancing.
2. Any gate failure triggers rollback to safe desktop path.

### Step 11: Validate Final Acceptance Criteria
Goal: define done using data, not assumptions.
Tasks:
1. Compare setup crash rate versus baseline.
2. Verify no malformed fingerprint combinations in logs.
3. Verify stable session success and error metrics.
Output:
1. Sign-off summary with before and after evidence.
Completion Criteria:
1. All acceptance gates are satisfied for the agreed observation window.

### Step 12: Deliver Operator Runbook
Goal: make operations and maintenance straightforward.
Tasks:
1. Document hardcoded constraint location in code.
2. Document fallback behavior and troubleshooting flow.
3. Document telemetry fields and interpretation.
4. Document rollback sequence to desktop-safe mode.
Output:
1. Updated runbook and change log entry.
Completion Criteria:
1. On-call operator can diagnose and recover without developer intervention.

## Per-File Task Breakdown

### app/browser/setup.py
1. Add constants block for strategy and hardcoded mobile constraints.
2. Add branching points for dry-run, active mobile path, and fallback.
3. Integrate mapper and validator before navigation.
4. Ensure persistent browser storage usage remains disabled.

### app/core/worker.py
1. Ensure fresh fingerprint generation is invoked per worker session.
2. Ensure session lifecycle includes telemetry start and outcome hooks.
3. Ensure fallback path preserves existing desktop execution behavior.

### app/core/telemetry.py
1. Add fingerprint lifecycle event helpers.
2. Add reason-code fields for validation and fallback.
3. Keep event schema stable and parseable for comparisons.

### docs/log/log-changes.md
1. Add implementation entries at each completed milestone.
2. Keep reverse-chronological format.

## Acceptance Gates
1. Setup crash rate does not increase beyond agreed tolerance.
2. Validator blocks malformed fingerprint combinations before navigation.
3. Fallback path is always available and functioning.
4. Fresh fingerprint per worker session is confirmed in telemetry evidence.
5. Persistent browser storage remains disabled throughout feature path.

## Rollout Gates

### Stage A Gate (Dry-Run)
1. Generation success rate meets target.
2. Validation failure reasons are understood and bounded.
3. No desktop flow regression observed.

### Stage B Gate (Limited Activation)
1. Mobile branch does not introduce instability beyond tolerance.
2. Fallback frequency remains within expected bound.
3. Critical path latency remains acceptable.

### Stage C Gate (Wider Activation)
1. Metrics remain stable across longer observation window.
2. Error patterns are not expanding.
3. Operations can execute rollback quickly if needed.

## Risk Register
1. Risk: generation timeout spikes under load.
Mitigation: timeout and one retry, then immediate fallback.
2. Risk: inconsistent fingerprint combinations pass into navigation.
Mitigation: strict preflight validator with reason-coded fail.
3. Risk: operational confusion from too many switches.
Mitigation: no new runtime config keys in this milestone.
4. Risk: fingerprint reuse across sessions.
Mitigation: enforce generation call per worker session and audit in telemetry.

## Deliverables Summary
1. Detailed execution plan and acceptance gates in this file.
2. No expansion of config.json for mobile strategy in this milestone.
3. Fresh fingerprint-per-worker requirement explicitly enforced in implementation steps.
4. Persistent browser storage disabled requirement explicitly enforced in implementation steps.

## Next Action After Plan Approval
1. Produce file-by-file execution checklist with exact function signatures and insertion locations.
2. Implement Phase 1 only after explicit go-ahead.

## Implementation Status (Completed)
1. Mobile fingerprint branch integrated in `app/browser/setup.py` using existing `device_type` runtime split.
2. Fresh fingerprint identity generation is invoked per mobile-selected worker session.
3. Preflight consistency validator blocks malformed combinations and emits reason-coded telemetry.
4. Desktop fallback is immediate on preflight failure and preserves stable session flow.
5. Persistent browser storage path is removed from runtime worker context creation.
6. Telemetry lifecycle events and session outcome segmentation are implemented.
7. Runbook delivered in `docs/runbook-mobile-fingerprint.md`.

## Go/No-Go Checklist Template
Use this checklist at each rollout stage.

### Stage A (Dry-Run)
1. [ ] Generation success rate meets target.
2. [ ] Validation reason codes are bounded and understood.
3. [ ] Desktop regression not observed.
4. Result: [ ] Go [ ] No-Go
5. Decision owner: __________
6. Date time: __________

### Stage B (Limited Activation)
1. [ ] Fallback frequency within expected range.
2. [ ] Setup crash rate within tolerance.
3. [ ] Latency impact acceptable.
4. Result: [ ] Go [ ] No-Go
5. Decision owner: __________
6. Date time: __________

### Stage C (Wider Activation)
1. [ ] Stability remains consistent over observation window.
2. [ ] No expanding error pattern in telemetry reason codes.
3. [ ] Rollback can be executed quickly by operators.
4. Result: [ ] Go [ ] No-Go
5. Decision owner: __________
6. Date time: __________
