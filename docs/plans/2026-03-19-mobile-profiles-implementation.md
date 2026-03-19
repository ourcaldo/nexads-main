# Mobile Fingerprint Integration Plan
Date: 2026-03-19

Goal
Build a maintainable mobile-profile integration path that uses BrowserForge-generated fingerprints with Playwright context settings, while keeping behavior consistent, measurable, and easy to operate in the current codebase.

Constraints (must-follow)
1. Keep mobile constraints hardcoded in code path for first milestone.
2. Do not add new runtime keys in config.json for mobile strategy in this milestone.
3. No persistent profiles for this feature path.
4. Every worker must use a fresh profile per worker session.
5. Keep desktop path behavior unchanged unless mobile branch is explicitly enabled in code.

Implementation Plan (Step by Step)

1. Define success criteria and operating constraints
Goal: prevent scope drift and unstable implementation decisions.
Actions:
1. Confirm primary objective is mobile-profile consistency in Playwright contexts.
2. Confirm fallback behavior when profile generation fails.
3. Confirm rollout mode is dry-run first, then guarded enablement.
Deliverable: written acceptance criteria and rollout gates in planning docs.

2. Baseline current launch flow and dependencies
Goal: identify exact integration points with minimal disruption.
Actions:
1. Trace browser/session creation path in app/browser/setup.py.
2. Trace session orchestration path in app/core/worker.py.
3. Verify current runtime toggles in config.json but do not add new keys.
Deliverable: one-page flow map of current desktop path.

3. Define in-code strategy constants (not config keys)
Goal: control rollout without expanding user-facing config complexity.
Actions:
1. Add hardcoded constants in setup path for mode: desktop-only, mobile-enabled, dry-run.
2. Add hardcoded mobile constraints in code: browser/os/device/screen bounds/locale policy.
3. Add hardcoded safety constants: max regeneration attempts and fallback behavior.
Deliverable: constants block in setup layer with comments and safe defaults.

4. Build fingerprint generation layer
Goal: generate full BrowserForge fingerprints per worker session with deterministic constraints.
Actions:
1. Create generation routine using hardcoded browser/os/device/screen constraints.
2. Return full fingerprint object plus normalized summary for logs.
3. Add retry and validation handling for strict or relaxed generation mode.
Deliverable: reusable generation function invoked by browser setup.

5. Implement context mapping (native Playwright subset)
Goal: apply highest-value and lowest-risk fingerprint fields natively.
Actions:
1. Map user agent, viewport, device scale factor, locale, and accepted headers.
2. Map mobile flags (is_mobile, has_touch) and perform consistency checks.
3. Bind exactly one fingerprint to one context/session and regenerate per worker session.
Deliverable: context-options mapper integrated into app/browser/setup.py.

6. Add consistency validator before navigation
Goal: block impossible combinations early.
Actions:
1. Validate UA family vs mobile flags vs viewport class.
2. Validate locale/header coherence.
3. If invalid, regenerate once or fallback based on in-code policy constants.
Deliverable: preflight validation gate in setup path.

7. Add optional advanced override mode behind strict flag
Goal: keep maintainability while allowing deeper experiments safely.
Actions:
1. Keep native mapping as default mode.
2. Add optional injector override mode behind explicit in-code opt-in.
3. Record applied vs not-applied fingerprint fields for observability.
Deliverable: guarded advanced mode with no default activation.

8. Instrument telemetry and diagnostics
Goal: make quality measurable and debuggable.
Actions:
1. Emit per-session profile summary and strategy mode.
2. Emit validation results and fallback reason codes.
3. Emit outcome metrics for comparison between desktop and mobile modes.
Deliverable: telemetry additions in app/core/telemetry.py and usage in app/core/worker.py.

9. Add dry-run execution path
Goal: validate generation and mapping without changing traffic behavior.
Actions:
1. Generate and validate fingerprints.
2. Log mapped context options only.
3. Skip full mobile execution when dry-run is enabled.
Deliverable: confidence-building stage before production rollout.

10. Execute staged rollout
Goal: reduce risk while collecting evidence.
Actions:
1. Stage A: 0% live use, dry-run only.
2. Stage B: small percentage sessions with fallback enabled.
3. Stage C: wider rollout after stability thresholds are met.
Deliverable: operational rollout checklist and go/no-go criteria.

11. Define acceptance criteria
Goal: clear done definition.
Actions:
1. No increase in setup crash rate.
2. No malformed profile/session combinations in logs.
3. Stable success/error metrics over agreed observation window.
Deliverable: sign-off report with before/after metrics.

12. Documentation and operator runbook
Goal: make future maintenance straightforward.
Actions:
1. Document hardcoded constraints and where they live in code.
2. Document fallback paths and troubleshooting steps.
3. Document telemetry fields and interpretation.
Deliverable: updated README/runbook and change-log entry in docs/log/log-changes.md.

Phase Goals
1. Phase 1: generation + native mapping + validation + telemetry.
2. Phase 2: optional advanced overrides behind feature flag.
3. Phase 3: optimization using observed production metrics.
| 4 | `app/browser/setup.py` | `validate_profile_consistency()`, tests | ~100 |
| 5 | `app/core/telemetry.py` | Event emission, metrics aggregation, tests | ~120 |
| 6 | Manual execution | Staged rollout logs, metrics comparison | – |
| 7 | `docs/MOBILE_PROFILES.md` | Operator runbook | ~250 |

**Total Implementation LOC:** ~750  
**Testing LOC:** ~300  
**Estimated Effort:** 6–8 hours (foundation to dry-run ready)

---

## Risk Mitigation

| Risk | Mitigation |
|------|----------|
| Fingerprint generation hangs | Timeout per task 1; fallback logic |
| Validation fails frequently | Relaxed rules + dry-run to calibrate |
| Mobile crashes session | Fallback to desktop; zero harm |
| Telemetry I/O blocks worker | Async telemetry or background thread |
| Config typos break startup | Validation on config load (task 2) |

---

## Success Metrics

- [ ] Dry-run completes with zero crashes
- [ ] Stage B (5%) shows ≤ 2% fallback rate
- [ ] Stage C (100%) reaches 100% mobile sessions with ≤ 1% crash increase
- [ ] Telemetry reveals no validation failures or generation errors
- [ ] Operator runbook enables on-call support

