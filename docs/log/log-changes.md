# Log Changes

## Entry
- Date time: 2026-03-19T08:38:51-07:00
- Short description: Push latest user-updated config and docs snapshot
- What you do: Staged and prepared all current non-cache workspace changes including updated configuration/runtime docs and telemetry data files for a single commit and push, excluding Python cache artifacts.
- File path that changes: AGENTS.md; README.md; config.json; data/worker_events.jsonl; data/ad_click_events.jsonl; data/telemetry_mobile.jsonl; data/worker_errors.jsonl; docs/log/log-changes.md

## Entry
- Date time: 2026-03-19T07:58:22-07:00
- Short description: Prevent hidden settings via scrollable tab containers
- What you do: Added scroll-area wrappers for all configuration tabs and vertical stretch balancing in general settings columns so sections like Session Settings remain accessible even when content exceeds viewport height.
- File path that changes: app/ui/config_window.py; docs/log/log-changes.md

## Entry
- Date time: 2026-03-19T07:56:37-07:00
- Short description: Rebalance GUI sizing proportions to avoid overlap
- What you do: Normalized typography and control sizing across tabs/groups/inputs/buttons, reduced oversized tab and button dimensions, removed the large dashboard header/subtitle block, and tightened layout spacing so large elements no longer crowd smaller controls.
- File path that changes: app/ui/config_window.py; docs/log/log-changes.md

## Entry
- Date time: 2026-03-19T07:54:24-07:00
- Short description: Improve GUI readability and overall UX styling
- What you do: Revamped PyQt configuration window visuals with larger default typography, improved tab/group/button/input styling, increased spacing and touch targets, added dashboard title/subtitle context, and improved table/header readability for easier configuration editing.
- File path that changes: app/ui/config_window.py; docs/log/log-changes.md

## Entry

## Entry

## Entry
 - Date time: 2026-03-19T06:39:40-07:00
 - Short description: Inline BrowserForge JSON format directly in AGENTS
 - What you do: Moved the full BrowserForge mobile fingerprint JSON example directly into AGENTS under the required mobile fingerprint section and removed the separate docs JSON sample file, keeping future reference in AGENTS as requested.
 - File path that changes: AGENTS.md; docs/browserforge-mobile-fingerprint-sample.json; docs/log/log-changes.md

## Entry
 - Date time: 2026-03-19T06:31:55-07:00
 - Short description: Add BrowserForge structure reference and full fingerprint injection path
 - What you do: Added permanent BrowserForge mobile fingerprint reference and sample structure in AGENTS/docs, switched mobile generation back to full FingerprintGenerator payload, carried full payload through setup, and injected full fingerprint data into mobile contexts via init script before page creation.
 - File path that changes: AGENTS.md; docs/browserforge-mobile-fingerprint-sample.json; app/browser/mobile.py; app/browser/setup.py; app/core/worker.py; docs/log/log-changes.md
## Entry
- Date time: 2026-03-19T05:56:02-07:00
- Short description: Fix telemetry kwargs crash after mobile fingerprint generation
- What you do: Expanded mobile fingerprint telemetry helper to accept and record locale/touch/client-hints fields plus future extra keyword fields, preventing runtime failures from unexpected telemetry arguments.
- File path that changes: app/core/telemetry.py; docs/log/log-changes.md

## Entry
- Date time: 2026-03-19T05:54:37-07:00
- Short description: Fix typed fingerprint field access for mobile generation
- What you do: Replaced dict-only field access with safe helpers that support both dict-like and typed BrowserForge objects for navigator/screen/headers, fixing runtime crashes such as NavigatorFingerprint missing get().
- File path that changes: app/browser/mobile.py; app/browser/setup.py; docs/log/log-changes.md

## Entry
- Date time: 2026-03-19T05:52:48-07:00
- Short description: Route mobile sessions to Playwright and keep Camoufox desktop-only
- What you do: Refactored browser setup so desktop sessions continue using Camoufox while mobile-selected sessions launch via Playwright (Chromium/WebKit) with proxy support, retained mobile fingerprint preflight and context mapping, and updated cleanup to stop Playwright managers.
- File path that changes: app/browser/setup.py; docs/log/log-changes.md

## Entry
- Date time: 2026-03-19T05:49:58-07:00
- Short description: Fix mobile launch and fingerprint pair compatibility
- What you do: Updated browser setup to use mobile-safe launch OS when a session is selected as mobile, preventing desktop/mobile header generation conflicts, and constrained fingerprint browser/OS sampling to valid pairs (chrome+android, safari+ios) with stable fallback.
- File path that changes: app/browser/setup.py; app/browser/mobile.py; docs/log/log-changes.md

## Entry
- Date time: 2026-03-19T05:46:09-07:00
- Short description: Remove dry-run branch from mobile fingerprint setup
- What you do: Removed the dry-run feature toggle and deleted the dry-run completion branch so mobile-selected sessions always run the active fingerprint path or fallback to desktop when preflight fails.
- File path that changes: app/browser/setup.py; docs/log/log-changes.md

## Entry
- Date time: 2026-03-19T05:42:31-07:00
- Short description: Complete remaining mobile fingerprint rollout and operations deliverables
- What you do: Added reason-code and strategy/session metadata fields to fingerprint telemetry, added advanced override guard in setup, expanded plan file with implementation status plus Stage A/B/C go-no-go checklist template, created a dedicated operator runbook with rollout gates and rollback procedure, and linked runbook in README.
- File path that changes: app/core/telemetry.py; app/browser/setup.py; app/core/worker.py; docs/plans/2026-03-19-mobile-profiles-implementation.md; docs/runbook-mobile-fingerprint.md; README.md; docs/log/log-changes.md

## Entry
- Date time: 2026-03-19T05:31:44-07:00
- Short description: Activate mobile fingerprint application for mobile sessions
- What you do: Changed setup strategy to disable dry-run so sessions selected as mobile by device_type now apply mapped mobile fingerprint context options instead of desktop dry-run behavior.
- File path that changes: app/browser/setup.py; docs/log/log-changes.md

## Entry
- Date time: 2026-03-19T05:21:18-07:00
- Short description: Re-align enhancement to mobile fingerprint branch with no persistent storage
- What you do: Implemented hardcoded mobile fingerprint branch controls in setup with desktop fallback and dry-run support, updated worker to consume setup context options while always starting fresh with non-persistent browser storage, switched telemetry/event wording to fingerprint terminology, and removed persistent storage setting from config and UI wiring.
- File path that changes: app/browser/setup.py; app/browser/mobile.py; app/core/worker.py; app/core/telemetry.py; app/ui/config_window.py; config.json; README.md; docs/log/log-changes.md

## Entry
- Date time: 2026-03-19T05:08:00-07:00
- Short description: Remove profile terminology from mobile fingerprint plan wording
- What you do: Updated the plan text to use fingerprint and session identity terminology, removed profile and persistent-profile wording in plan body, and clarified that persistent browser storage is disabled while fresh fingerprint generation is per worker session.
- File path that changes: docs/plans/2026-03-19-mobile-profiles-implementation.md

## Entry
- Date time: 2026-03-19T04:58:00-07:00
- Short description: Expand mobile integration plan with full detailed scope and hard constraints
- What you do: Replaced the mobile integration planning doc with a comprehensive step-by-step implementation plan that includes explicit per-step tasks, completion criteria, per-file breakdown, acceptance gates, rollout gates, and risk register while enforcing hardcoded mobile constraints, no new config keys, fresh profile per worker session, and persistent-profile disabled behavior.
- File path that changes: docs/plans/2026-03-19-mobile-profiles-implementation.md

## Entry
- Date time: 2026-03-19T04:40:00-07:00
- Short description: Reset to plan-only state and remove accidental mobile config additions
- What you do: Rewrote mobile fingerprint document as implementation plan only in docs/plans, restored planning-first copilot instruction wording, and removed unintended mobile strategy keys from config.json so mobile constraints remain hardcoded in code planning scope.
- File path that changes: docs/plans/2026-03-19-mobile-profiles-implementation.md; .github/copilot-instructions.md; config.json

## Entry
- Date time: 2026-03-19T15:30:00-07:00
- Short description: Implement Phase 1 of mobile device fingerprint support (Tasks 1-5)
- What you do: Created app/browser/mobile.py with BrowserForge-based fingerprint generation. Extended app/browser/setup.py with mobile branch (configure_mobile_browser), fingerprint-to-context mapping (map_fingerprint_to_context_options), and consistency validation (validate_profile_consistency). Added mobile profile telemetry to app/core/telemetry.py with emit_mobile_profile_event(). Extended config.json with profile_strategy, mobile_constraints, and telemetry settings. Updated .github/copilot-instructions.md to enforce code implementation over planning. Created comprehensive implementation plan at docs/plans/2026-03-19-mobile-profiles-implementation.md.
- File path that changes: app/browser/mobile.py; app/browser/setup.py; app/core/telemetry.py; config.json; .github/copilot-instructions.md; docs/plans/2026-03-19-mobile-profiles-implementation.md

## Entry
- Date time: 2026-03-19 01:40:12 -07:00
- Short description: Clean implemented content from enhancement plan
- What you do: Removed detailed sections that were already implemented and kept the plan focused on pending scope only (Section 15 and pending checklist under Section 20).
- File path that changes: docs/plans/enhancement-plan.md

## Entry
- Date time: 2026-03-19 01:39:25 -07:00
- Short description: Move change log file to docs/log path
- What you do: Moved log changes file from docs/plans to docs/log and updated copilot instructions to require updates at docs/log/log-changes.md.
- File path that changes: docs/log/log-changes.md; .github/copilot-instructions.md

## Entry
- Date time: 2026-03-19 01:37:35 -07:00
- Short description: Add mandatory log-changes policy to copilot instructions
- What you do: Added a new Change Log Rules section requiring updates to docs/log/log-changes.md before commit/push, with exact required fields and newest-first ordering.
- File path that changes: .github/copilot-instructions.md

## Entry
- Date time: 2026-03-19T01:28:17-07:00
- Short description: Implement section 19 worker telemetry json streams
- What you do: Added structured worker telemetry emission with dual JSONL outputs (all events and failures-only), instrumented worker lifecycle steps, and updated enhancement tracker status.
- File path that changes: app/core/telemetry.py; app/core/worker.py; docs/plans/enhancement-plan.md

## Entry
- Date time: 2026-03-19T01:00:25-07:00
- Short description: Align same-tab ad dwell with existing ads min/max
- What you do: Removed hardcoded same-tab dwell clamp so same-tab ad stay uses existing ads min/max behavior and updated section 18 plan scope/status.
- File path that changes: app/core/worker.py; docs/plans/enhancement-plan.md

## Entry
- Date time: 2026-03-19T00:42:09-07:00
- Short description: Implement section 17 intent-aware redirect guard
- What you do: Added NavigationIntent model, intent-aware domain matching, reason codes, and per-intent redirect budgets with worker integration and summary counters.
- File path that changes: app/navigation/tabs.py; app/core/worker.py; docs/plans/enhancement-plan.md

## Entry
- Date time: 2026-03-19T00:17:36-07:00
- Short description: Complete section 14 ad outcome pipeline persistence
- What you do: Added full ad click outcome payload fields (including click_id and timestamps), persisted events to JSONL, and kept legacy binary success flag.
- File path that changes: app/ads/outcomes.py; app/ads/adsense.py; docs/plans/enhancement-plan.md

## Entry
- Date time: 2026-03-18T15:04:25-07:00
- Short description: Add universal consent handler with GDPR gating
- What you do: Implemented shared consent handling with interception-aware flow and integrated policy-based unresolved consent behavior in worker session flow.
- File path that changes: app/navigation/consent.py; app/navigation/referrer.py; app/core/worker.py; README.md; config.json; proxy.txt
