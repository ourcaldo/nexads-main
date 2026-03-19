"""
nexads/core/telemetry.py
Structured worker telemetry event helpers.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

_PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DEFAULT_EVENTS_OUTPUT = _PKG_ROOT / "data" / "worker_events.jsonl"
DEFAULT_ERRORS_OUTPUT = _PKG_ROOT / "data" / "worker_errors.jsonl"
DEFAULT_MOBILE_PROFILE_OUTPUT = _PKG_ROOT / "data" / "telemetry_mobile.jsonl"


def _extract_domain(url: str) -> str:
    """Extract normalized domain from URL."""
    try:
        host = (urlparse(url or "").hostname or "").strip().lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _append_jsonl(path: pathlib.Path, event: dict) -> bool:
    """Append one event line to a JSONL file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def emit_worker_event(*,
                      worker_id: int,
                      session_id: str,
                      step_name: str,
                      status: str,
                      url_index: int | None = None,
                      url: str = "",
                      intent_type: str = "",
                      reason_code: str = "",
                      error_type: str = "",
                      error_message: str = "",
                      duration_ms: int | None = None,
                      meta: dict | None = None,
                      events_output: pathlib.Path | str = DEFAULT_EVENTS_OUTPUT,
                      errors_output: pathlib.Path | str = DEFAULT_ERRORS_OUTPUT) -> bool:
    """Emit one worker telemetry event and mirror failures into error stream."""
    event = {
        "event_id": f"evt_{uuid4().hex}",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "worker_id": int(worker_id),
        "session_id": str(session_id),
        "url_index": int(url_index) if url_index is not None else None,
        "step_name": str(step_name),
        "status": str(status),
        "url": str(url or ""),
        "domain": _extract_domain(url),
        "intent_type": str(intent_type or ""),
        "reason_code": str(reason_code or ""),
        "error_type": str(error_type or ""),
        "error_message": str(error_message or ""),
        "duration_ms": int(duration_ms) if duration_ms is not None else None,
        "meta": meta if isinstance(meta, dict) else {},
    }

    events_path = pathlib.Path(events_output)
    errors_path = pathlib.Path(errors_output)

    wrote_events = _append_jsonl(events_path, event)
    wrote_errors = True

    if str(status).lower() == "failed":
        wrote_errors = _append_jsonl(errors_path, event)

    if not wrote_events:
        print(
            f"Worker {worker_id}: Telemetry warning - could not write "
            f"worker event to {events_path}"
        )
    if not wrote_errors:
        print(
            f"Worker {worker_id}: Telemetry warning - could not write "
            f"worker error event to {errors_path}"
        )

    return wrote_events and wrote_errors


# --- Mobile Profile Telemetry (Task 5) ---

def emit_mobile_profile_event(
    *,
    worker_id: int,
    event_type: str,
    browser_family: str | None = None,
    os: str | None = None,
    ua_snippet: str | None = None,
    platform: str | None = None,
    viewport: str | None = None,
    dpr: float | None = None,
    generation_ms: int | None = None,
    is_valid: bool | None = None,
    violation_count: int | None = None,
    violations: list | None = None,
    reason: str | None = None,
    fallback_target: str | None = None,
    final_mode: str | None = None,
    success: bool | None = None,
    error_code: str | None = None,
    output: pathlib.Path | str = DEFAULT_MOBILE_PROFILE_OUTPUT
) -> bool:
    """
    Emit mobile profile telemetry event (Task 5).
    
    Args:
        worker_id: Worker ID
        event_type: "profile_generation_started", "profile_generated", "profile_validation_result", 
                    "profile_fallback_triggered", "context_created", "session_outcome"
        browser_family: Browser family (chrome, safari, etc.)
        os: OS (android, ios)
        ua_snippet: User-Agent snippet (first 60 chars)
        platform: Platform string (Linux, iPhone, etc.)
        viewport: Viewport string like "393x873"
        dpr: Device pixel ratio
        generation_ms: Generation time in ms
        is_valid: Validation result (True/False)
        violation_count: Number of validation violations
        violations: List of violation strings
        reason: Reason for fallback/failure
        fallback_target: Fallback target (desktop, none)
        final_mode: Final mode (mobile, desktop)
        success: Session outcome success
        error_code: Error code if failed
        output: Output file path
    
    Returns:
        True if written, False otherwise
    """
    event = {
        "event_id": f"mp_{uuid4().hex}",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "worker_id": int(worker_id),
        "event_type": str(event_type),
        "browser_family": browser_family,
        "os": os,
        "ua_snippet": ua_snippet,
        "platform": platform,
        "viewport": viewport,
        "dpr": dpr,
        "generation_ms": generation_ms,
        "is_valid": is_valid,
        "violation_count": violation_count,
        "violations": violations or [],
        "reason": reason,
        "fallback_target": fallback_target,
        "final_mode": final_mode,
        "success": success,
        "error_code": error_code,
    }
    
    # Remove None values for cleaner JSON
    event = {k: v for k, v in event.items() if v is not None}
    
    output_path = pathlib.Path(output)
    wrote = _append_jsonl(output_path, event)
    
    if not wrote:
        print(f"Worker {worker_id}: Telemetry warning - could not write mobile profile event to {output_path}")
    
    return wrote

