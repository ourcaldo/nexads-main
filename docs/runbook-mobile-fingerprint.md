# Mobile Fingerprint Operator Runbook

Date: 2026-03-19

## Purpose
Operate, validate, and rollback the mobile fingerprint path safely while preserving desktop fallback.

## Scope
- Uses existing `device_type.mobile` / `device_type.desktop` runtime split in `config.json`.
- Does not use persistent browser storage.
- No additional runtime keys are required.

## Hardcoded Strategy Location
- Strategy constants: `app/browser/setup.py`
- Fingerprint generation: `app/browser/mobile.py`
- Worker lifecycle + session telemetry: `app/core/worker.py`
- Telemetry writer: `app/core/telemetry.py`

## Runtime Activation
1. Set `device_type.mobile` > 0 in `config.json` to allow mobile fingerprint sessions.
2. Keep `device_type.desktop` > 0 for mixed traffic and safe fallback behavior.
3. Mobile path is selected per-session by weighted choice from existing config.

## Fallback Behavior
When mobile fingerprint preflight fails:
1. Emit `fingerprint_fallback_triggered` event with reason and reason codes.
2. Session continues with stable desktop context path.
3. Worker session remains alive; no worker crash is expected.

## Telemetry Files
- `data/telemetry_mobile.jsonl`: fingerprint lifecycle events.
- `data/worker_events.jsonl`: worker step telemetry.
- `data/worker_errors.jsonl`: failed worker events.

## Key Fingerprint Events
- `fingerprint_flow_started`
- `fingerprint_validation_result`
- `fingerprint_regeneration`
- `fingerprint_fallback_triggered`
- `fingerprint_dry_run_completed`
- `mobile_context_ready`
- `session_fingerprint_mode`
- `session_outcome`

## Reason Code Interpretation
Common reason codes and action:
- `generation_failed`: BrowserForge generation returned no fingerprint; inspect runtime and package state.
- `mobile_flag_mismatch`: fingerprint/userAgent mapping mismatch; inspect mapping logic.
- `touch_flag_mismatch`: touch capability inconsistent; inspect mapping and fingerprint fields.
- `ua_platform_mismatch_android` / `ua_platform_mismatch_ios`: UA/platform mismatch.
- `viewport_width_out_of_bounds` / `viewport_height_out_of_bounds`: outside hardcoded mobile bounds.
- `locale_header_mismatch`: locale and `Accept-Language` mismatch.

## Acceptance Gate Checklist
1. Setup crash rate does not regress beyond baseline tolerance.
2. Validation blocks malformed combinations before navigation.
3. Desktop fallback remains available and functional.
4. Fingerprint lifecycle exists for each mobile-selected session in telemetry.
5. Persistent browser storage remains disabled in runtime flow.

## Rollout Stages
### Stage A (Dry-run)
1. Keep mobile selection enabled via `device_type.mobile`.
2. Set `MOBILE_FINGERPRINT_DRY_RUN = True` in `app/browser/setup.py`.
3. Verify telemetry coverage and validation reason distribution.

### Stage B (Limited activation)
1. Set `MOBILE_FINGERPRINT_DRY_RUN = False`.
2. Keep `device_type.mobile` low (example 5-20).
3. Watch fallback frequency and setup stability.

### Stage C (Wider activation)
1. Increase `device_type.mobile` gradually.
2. Confirm no expanding error patterns.
3. Maintain rollback readiness.

## Rollback Procedure
1. Immediate safe rollback: set `device_type.mobile = 0` and `device_type.desktop = 100` in `config.json`.
2. Optional code-level rollback: set `MOBILE_FINGERPRINT_DRY_RUN = True` in `app/browser/setup.py`.
3. Confirm `session_fingerprint_mode` and `session_outcome` events show desktop-only path.

## Troubleshooting Flow
1. Check `telemetry_mobile.jsonl` for latest `fingerprint_fallback_triggered` and reason codes.
2. Correlate worker/session IDs with `worker_events.jsonl`.
3. If generation repeatedly fails, verify browserforge/camoufox environment installation.
4. If validation fails often, inspect reason code trends and mapping bounds.
