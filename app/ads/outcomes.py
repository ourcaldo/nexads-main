"""
nexads/ads/outcomes.py
Shared ad click outcome tracking, classification, and confidence scoring.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from app.ads.signals import load_adsense_signals_payload


_PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DEFAULT_EVENTS_OUTPUT = _PKG_ROOT / "data" / "ad_click_events.jsonl"


def _extract_domain(url: str) -> str:
    """Extract normalized domain from URL."""
    try:
        netloc = urlparse(url or "").netloc.lower().strip()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        clean = (item or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def _load_known_ad_hosts(limit: int = 500) -> set[str]:
    payload = load_adsense_signals_payload()
    hosts = payload.get("signals", {}).get("network_hosts", [])
    if not isinstance(hosts, list):
        return set()
    return {str(h).strip().lower() for h in hosts[:max(0, int(limit))] if str(h).strip()}


def persist_ad_click_event(event: dict,
                           output_path: pathlib.Path | str = DEFAULT_EVENTS_OUTPUT) -> bool:
    """Append one ad click outcome event as JSONL for later analysis."""
    try:
        out_path = pathlib.Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def classify_destination(source_domain: str,
                         final_domain: str,
                         redirect_chain: list[str],
                         known_ad_hosts: set[str]) -> tuple[str, list[str]]:
    """Classify click destination and provide reason codes."""
    reasons: list[str] = []

    if not final_domain:
        return "blocked_or_failed", ["missing_final_domain"]

    if final_domain == source_domain:
        reasons.append("same_domain_final")

    chain_domains = [_extract_domain(url) for url in redirect_chain]
    chain_domains = [d for d in chain_domains if d]

    ad_host_hit = any(
        any(domain == host or domain.endswith(f".{host}") for host in known_ad_hosts)
        for domain in chain_domains + [final_domain]
    )
    if ad_host_hit:
        reasons.append("ad_host_signature")

    if final_domain != source_domain:
        reasons.append("cross_domain_navigation")

    if ad_host_hit and final_domain != source_domain:
        return "ad_destination", reasons

    if final_domain == source_domain:
        return "same_site_internal", reasons

    return "uncertain", reasons


def score_click_outcome(outcome_type: str,
                        source_url: str,
                        final_url: str,
                        classification: str,
                        reason_codes: list[str],
                        redirect_chain: list[str]) -> float:
    """Compute confidence score in [0, 1] for ad click validity."""
    score = 0.0

    if outcome_type == "new_tab_navigation":
        score += 0.25
    elif outcome_type == "same_tab_navigation":
        score += 0.18

    if final_url and final_url != source_url:
        score += 0.25
    else:
        score -= 0.20

    if any(code == "ad_host_signature" for code in reason_codes):
        score += 0.20

    if len(redirect_chain) >= 2:
        score += 0.10

    if classification == "ad_destination":
        score += 0.20
    elif classification == "blocked_or_failed":
        score -= 0.30
    elif classification == "same_site_internal":
        score -= 0.12

    return max(0.0, min(1.0, score))


async def evaluate_ad_click_outcome(page, context,
                                    source_url: str,
                                    source_domain: str,
                                    tabs_before: int,
                                    monitor_seconds: float = 5.0) -> dict:
    """Track navigation outcome after click and return normalized event payload."""
    click_id = f"clk_{uuid4().hex}"
    started_at = datetime.now(timezone.utc)
    redirect_chain: list[str] = [source_url]

    def _on_frame_navigated(frame):
        try:
            if frame == page.main_frame:
                redirect_chain.append(frame.url)
        except Exception:
            pass

    try:
        page.on("framenavigated", _on_frame_navigated)
    except Exception:
        _on_frame_navigated = None

    try:
        await page.wait_for_timeout(int(max(0.5, monitor_seconds) * 1000))
    except Exception:
        pass
    finally:
        if _on_frame_navigated is not None:
            try:
                page.remove_listener("framenavigated", _on_frame_navigated)
            except Exception:
                pass

    final_url = ""
    try:
        final_url = page.url or ""
    except Exception:
        final_url = ""

    if final_url:
        redirect_chain.append(final_url)

    redirect_chain = _dedupe_preserve_order(redirect_chain)

    tabs_after = len(context.pages)
    if tabs_after > tabs_before:
        outcome_type = "new_tab_navigation"
    elif final_url and final_url != source_url:
        outcome_type = "same_tab_navigation"
    else:
        outcome_type = "no_navigation"

    final_domain = _extract_domain(final_url)
    known_hosts = _load_known_ad_hosts()
    classification, reason_codes = classify_destination(
        source_domain=source_domain,
        final_domain=final_domain,
        redirect_chain=redirect_chain,
        known_ad_hosts=known_hosts,
    )

    if outcome_type == "no_navigation":
        reason_codes.append("no_navigation_after_click")

    confidence_score = score_click_outcome(
        outcome_type=outcome_type,
        source_url=source_url,
        final_url=final_url,
        classification=classification,
        reason_codes=reason_codes,
        redirect_chain=redirect_chain,
    )

    finished_at = datetime.now(timezone.utc)

    return {
        "click_id": click_id,
        "event_type": "ad_click_outcome",
        "created_at_utc": started_at.isoformat(),
        "completed_at_utc": finished_at.isoformat(),
        "source_url": source_url,
        "source_domain": source_domain,
        "tabs_before": tabs_before,
        "tabs_after": tabs_after,
        "outcome_type": outcome_type,
        "redirect_chain": redirect_chain,
        "final_url": final_url,
        "final_domain": final_domain,
        "classification": classification,
        "confidence_score": confidence_score,
        "reason_codes": reason_codes,
        "timings_ms": {
            "monitor_window": int(max(0.5, monitor_seconds) * 1000),
        },
    }
