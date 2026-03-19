# Mobile Device Fingerprint Support Implementation Plan
**Date:** March 19, 2026  
**Objective:** Add realistic mobile device profile generation to Playwright browser automation using BrowserForge.

---

## Phase Overview

| Phase | Tasks | Success Criteria |
|-------|-------|------------------|
| **Phase 1: Foundation & Integration** | 1–4 | Generation, mapping, validation working; no live impact |
| **Phase 2: Telemetry & Dry-Run** | 5–6a | Metrics collected; Stage A dry-run stable |
| **Phase 3: Staged Rollout** | 6b–6d | Gradual live rollout; acceptance gates passed |

---

## Task 1: Create Mobile Fingerprint Generation Layer
**File:** `app/browser/mobile.py` (new)  
**Goal:** Generate BrowserForge fingerprints constrained to mobile device specs.

**Inputs:**
- `domain: str` — target domain (used for locale matching)
- `browser_family: str` — "chrome", "safari", "firefox", "edge"
- `os: str` — "android", "ios"
- `device_type: str` — "mobile" (hardcoded)
- `screen_constraints: Dict` — min/max width/height
- `config: Dict` — includes `fingerprint_generation_retry_policy`

**Outputs:**
- `Fingerprint` dataclass (from BrowserForge)
- Fallback: `None` if generation fails and fallback_policy = "fail_safe"

**Behavior:**
1. Create BrowserForge `FingerprintGenerator()` instance
2. Build `Screen(min_width=..., max_width=..., min_height=..., max_height=...)`
3. Call `generator.generate(browser=browser_family, os=os, device='mobile', screen=screen)`
4. On exception: Log error, retry per `config['fingerprint_generation_retry_policy']`, fallback to desktop or None
5. Return real Fingerprint or fallback value

**Tests:**
- `test_generate_android_chrome()` → returns UA with "Mobile", platform="Linux"
- `test_generate_ios_safari()` → returns UA with "iPhone", platform="iPhone"
- `test_generate_with_retry_policy()` → verifies retry/fallback on exception

**Code Location:** Will be called from `app/browser/setup.py` in new mobile branch (Task 2).

---

## Task 2: Extend Browser Setup to Support Mobile Profiles
**File:** `app/browser/setup.py` (existing, modified)  
**Goal:** Accept mobile profile strategy and branch launch path.

**New Function:** `configure_mobile_browser()`
- Input: `config: Dict`, `worker_id: int`
- Output: `browser`, `context` tuples configured with mobile profiles
- Logic:
  1. Determine if mobile mode enabled via `config['profile_strategy']` == "mobile-enabled"
  2. Load constraints from `config['mobile_constraints']`
  3. Call Task 1 generation layer for each session
  4. Map fingerprint to context via Task 3 (below)
  5. Create Playwright context with Task 3 mapped options
  6. Log profile summary per worker

**Modified:** `configure_browser()` function
- Add parameter: `mobile_mode: bool = False`
- Add branch: `if mobile_mode: return configure_mobile_browser(...)`
- Keep existing Camoufox path for desktop untouched

**Tests:**
- `test_configure_mobile_browser_returns_context()` → context has correct UA/viewport
- `test_fallback_to_desktop_on_generation_fail()` → graceful fallback if fingerprint = None
- `test_headless_flag_respected()` → mobile context respects headless_mode config

---

## Task 3: Build Fingerprint-to-Context Mapper
**File:** `app/browser/setup.py` (add function)  
**Goal:** Map BrowserForge Fingerprint fields to Playwright context options.

**Function:** `map_fingerprint_to_context_options(fingerprint: Fingerprint, profile_summary: Dict) -> Dict`

**Mapping Logic:**
```
BrowserForge Field              → Playwright Context Option
fingerprint.navigator.userAgent → user_agent
fingerprint.screen.width        → viewport['width']
fingerprint.screen.height       → viewport['height']
fingerprint.screen.dpr          → device_scale_factor
(is_mobile flag)                → is_mobile=True
fingerprint.navigator.maxTouchPoints (> 0) → has_touch=True
fingerprint.navigator.language  → locale
fingerprint.headers (all)       → extra_http_headers (Dict)
```

**Output:** Dict matching `browser.new_context(**mapped_options)`

**Optional Overrides:** (if `config['fingerprint_advanced_overrides']` enabled)
- `codecs`: map videoCodecs/audioCodecs to navigator override JS (not native Playwright)
- `webglVendor`, `webglRenderer`: plugin detection bypass (JS injection only)
- Note: Advanced overrides require Camoufox interception or JS evaluation post-context creation

**Tests:**
- `test_map_ua_only()` → user_agent set correctly
- `test_map_viewport_and_dpr()` → viewport and device_scale_factor set
- `test_map_all_headers()` → extra_http_headers populated from fingerprint

---

## Task 4: Implement Consistency Validator
**File:** `app/browser/setup.py` (add function)  
**Goal:** Validate mapped fingerprint consistency before context creation.

**Function:** `validate_profile_consistency(fingerprint: Fingerprint, context_opts: Dict, profile_summary: Dict) -> Tuple[bool, List[str]]`

**Validation Rules:**
1. **Mobile Flag Consistency**: If "Mobile" in user_agent, then is_mobile=True
2. **Touch Consistency**: If maxTouchPoints > 0, then has_touch=True
3. **Locale Coherence**: Accept-Language header matches locale param (both use same language code)
4. **Platform Realism**:
   - Android UA must have platform="Linux armv*"
   - iOS UA must have platform="iPhone" or "iPad"
5. **Impossible Combos**:
   - iOS + maxTouchPoints < 5 (invalid)
   - Android UA without "Mobile" (invalid for android)

**Output:** `(is_valid: bool, violations: List[str])`
- Valid: `(True, [])`
- Invalid: `(False, ["Platform mismatch: iOS UA found with platform=Linux", ...])`

**On Invalid:**
- If `config['profile_consistency_policy']` == "block": Log error, fallback per fallback_policy
- If `config['profile_consistency_policy']` == "regenerate": Log warning, retry generation once

**Tests:**
- `test_valid_android_profile()` → (True, [])
- `test_invalid_ios_with_android_platform()` → (False, ["Platform mismatch: ..."])
- `test_regenerate_on_invalid()` → verifies retry logic

---

## Task 5: Add Telemetry & Observability
**File:** `app/core/telemetry.py` (extend or create)  
**Goal:** Instrument mobile profile workflow for monitoring and debugging.

**Events to Log (per session):**
1. `profile_generation_started` → worker_id, browser_family, os, timestamp
2. `profile_generated` → fingerprint summary (UA snippet, platform, viewport), generation_ms
3. `profile_validation_result` → is_valid, violation_count, violation_list
4. `profile_fallback_triggered` → reason (exception | invalid | config_disabled), fallback_target (desktop | none)
5. `context_created` → worker_id, final_mode (mobile | desktop), context_opts_summary
6. `session_outcome` → worker_id, mode, success, error_code (if failed)

**Metrics to Emit (per batch/hourly):**
- Total sessions by mode (mobile vs desktop)
- Profile generation success rate (%)
- Validation failure rate (%)
- Fallback rate by reason (exception, validation, config)
- Session crash rate by mode (should not increase for mobile)
- Average session duration by mode

**Output:** Write to `data/telemetry_mobile.jsonl` (per-line JSON)

**Tests:**
- `test_telemetry_logs_generation_event()` → file contains generation event
- `test_telemetry_aggregates_metrics()` → hourly summary includes counts/rates

---

## Task 6: Execute Staged Rollout

### Stage A: Dry-Run (0% live traffic, 100% logging)
**Duration:** 1 session batch  
**What happens:**
- Profile generation enabled
- Validation enabled
- Fallback: Always fallback to desktop (never use mobile in live session)
- Observability: Full telemetry with no risk

**Success Criteria:**
- No crashes from generation/validation code
- No "None" fingerprints returned (all generations succeed or fallback gracefully)
- Profile validation pass rate ≥ 99%
- Telemetry event count = expected session count

**Go/No-Go Decision:** If any crash or generation error → review logs, fix, re-run Stage A. Else proceed to Stage B.

### Stage B: Small Live Sample (5% of sessions, fallback enabled)
**Duration:** 50–100 sessions  
**What happens:**
- `config['profile_strategy']` = "mobile-enabled"
- `config['profile_strategy_rollout_percentage']` = 5
- Fallback: If validation fails or exception, fallback to desktop (user is not harmed)
- Observability: Full telemetry with per-worker granularity

**Success Criteria:**
- Zero uncaught exceptions in mobile path (all errors logged + fallback)
- Mobile session crash rate ≤ desktop baseline + 0.5%
- Fallback rate ≤ 5% (i.e., 95% mobile sessions reach validation pass)
- User-visible metrics stable (duration, engagement, ad clicks)

**Go/No-Go Decision:** If crash rate up or fallback rate > 10% → investigate logs, fix, re-run Stage B. Else proceed to Stage C.

### Stage C: Gradual Rollout (10% → 25% → 50% → 100%)
**Duration Per Step:** 100–200 sessions  
**Progression:**
1. **Step 1 (10%)**: Run 100 sessions, monitor for 1 hour. If stable → proceed.
2. **Step 2 (25%)**: Run 200 sessions, monitor for 2 hours. If stable → proceed.
3. **Step 3 (50%)**: Run 500 sessions, monitor for 4 hours. If stable → proceed.
4. **Step 4 (100%)**: Full rollout; monitor continuously.

**Go/No-Go Criteria Per Step:**
- Crash rate stable (no increase > 0.5%)
- Fallback rate < 5%
- Error logs show no new patterns
- User-facing metrics (session duration, engagement, ad impressions) ≥ baseline

**Decision Points:**
- If any step fails criteria → stop rollout, investigate, fix, re-test
- If all steps pass → mobile profiles are production-ready

---

## Task 6a: Dry-Run Execution
**Manual Steps:**
1. Set `config['profile_strategy']` = "mobile-enabled" (testing)
2. Set `config['profile_strategy_rollout_percentage']` = 0 (force fallback to desktop)
3. Run `python main.py` for 1 session batch
4. Check `data/telemetry_mobile.jsonl` for generation/validation events
5. Verify no crashes in console/worker logs
6. Verify fallback always triggered (all use desktop mode, not mobile)

**Expected Output:**
```
data/telemetry_mobile.jsonl:
{"event": "profile_generation_started", "worker_id": 0, ...}
{"event": "profile_generated", "worker_id": 0, "ua_snippet": "Mozilla/5.0 (Android ...", ...}
{"event": "profile_validation_result", "worker_id": 0, "is_valid": true, ...}
{"event": "profile_fallback_triggered", "worker_id": 0, "reason": "config_disabled", "fallback_target": "desktop"}
{"event": "context_created", "worker_id": 0, "final_mode": "desktop", ...}
{"event": "session_outcome", "worker_id": 0, "mode": "desktop", "success": true}
```

---

## Task 6b: Stage B Execution (5% Live Sample)
**Manual Steps:**
1. Set `config['profile_strategy']` = "mobile-enabled"
2. Set `config['profile_strategy_rollout_percentage']` = 5
3. Run `python main.py` for 50–100 sessions
4. Monitor console output and `data/telemetry_mobile.jsonl` in real-time
5. Count crashes, fallbacks, validation failures

**Expected Outcome:**
- ~5% of sessions use mobile mode (rest use desktop)
- ~1% of mobile sessions fallback (validation or exception)
- Zero uncaught exceptions
- Session durations/outcomes consistent with baseline

---

## Task 6c: Stage C Execution (10% → 25% → 50% → 100%)
**Manual Steps (per step):**
1. Update `config['profile_strategy_rollout_percentage']` to target (10, 25, 50, 100)
2. Run `python main.py` for N sessions (100 → 200 → 500)
3. Monitor telemetry and user-facing metrics
4. If stable, proceed to next step; else diagnose and fix

---

## Task 7: Documentation & Operator Runbook
**File:** `docs/MOBILE_PROFILES.md` (new)  
**Contents:**
1. **Overview**: What mobile profiles are, why they exist, what BrowserForge provides
2. **Configuration**: Schema for `config.json` (profile_strategy, mobile_constraints, etc.)
3. **Enabling Mobile Mode**: Step-by-step for ops team
4. **Monitoring**: How to read telemetry, what metrics indicate problems
5. **Troubleshooting**: Common failures (generation timeout, validation error, etc.) and resolutions
6. **Rollback**: How to disable mobile mode and fall back to desktop-only

---

## Configuration Schema (Task 2 + Config Extension)

**New keys in `config.json`:**
```json
{
  "profile_strategy": "desktop-only|mobile-enabled|dry-run",
  "profile_strategy_rollout_percentage": 0,
  "mobile_constraints": {
    "screen": {
      "min_width": 360,
      "max_width": 430,
      "min_height": 740,
      "max_height": 932
    },
    "browsers": ["chrome", "safari", "firefox"],
    "os": ["android", "ios"],
    "locales": ["en-US", "en-GB", "fr-FR"]
  },
  "fingerprint_generation_retry_policy": "regenerate_once",
  "fingerprint_generation_timeout_ms": 5000,
  "profile_consistency_policy": "block",
  "profile_fallback_policy": "fallback_to_desktop",
  "fingerprint_advanced_overrides": false,
  "telemetry": {
    "mobile_profiles_enabled": true,
    "output_file": "data/telemetry_mobile.jsonl"
  }
}
```

---

## Summary of Deliverables

| Task | File | Artifact | LOC |
|------|------|----------|-----|
| 1 | `app/browser/mobile.py` | `generate_mobile_fingerprint()`, tests | ~150 |
| 2 | `app/browser/setup.py` | `configure_mobile_browser()`, branch logic, tests | ~100 |
| 3 | `app/browser/setup.py` | `map_fingerprint_to_context_options()`, tests | ~80 |
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

