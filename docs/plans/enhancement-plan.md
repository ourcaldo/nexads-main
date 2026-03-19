## Implementation Tracker

| Section | Area | Status | Notes |
|---|---|---|---|
| 14 | Ad Outcome Validation Pipeline | Implemented | Implemented and tracked in logs. Detailed design notes removed from this active plan. |
| 15 | Multi-Network Ad Detection (Beyond AdSense) | Not Started | Active remaining enhancement scope. |
| 16 | GDPR Consent Failure: Click Interception Handling | Implemented | Implemented and tracked in logs. Detailed design notes removed from this active plan. |
| 17 | Redirect-Resilient Navigation Guard | Implemented | Implemented and tracked in logs. Detailed design notes removed from this active plan. |
| 18 | Same-Tab Ad Landing Handling (Keep It Simple) | Implemented | Implemented and tracked in logs. Detailed design notes removed from this active plan. |
| 19 | Step-Level Crash and Failure Telemetry | Implemented | Implemented and tracked in logs. Detailed design notes removed from this active plan. |
| 20 | Prioritized Next Sprint Checklist | In Progress | Only pending items remain below. |

Status legend: `Not Started`, `In Progress`, `Implemented`.

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

## 20. Pending Checklist

1. P1: Implement Section 15 multi-network ad detection.
2. P1: Add remaining session-end counters:
- same_tab_ad_returns
- consent_unresolved_count.
3. P2: Persist daily aggregated metrics snapshot to data/session_metrics.json.
