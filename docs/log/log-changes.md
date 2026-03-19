# Log Changes

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
