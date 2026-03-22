"""
nexads/ads/outcomes.py
Shared ad click outcome tracking, classification, and confidence scoring.
"""

from __future__ import annotations

import json
import pathlib
import random
from datetime import datetime, timezone
from uuid import uuid4

from app.ads.signals import load_adsense_signals_payload
from app.navigation.urls import extract_domain


_PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DEFAULT_EVENTS_OUTPUT = _PKG_ROOT / "data" / "ad_click_events.jsonl"


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


_known_ad_hosts_cache: set[str] | None = None


def _load_known_ad_hosts(limit: int = 500) -> set[str]:
    global _known_ad_hosts_cache
    if _known_ad_hosts_cache is not None:
        return _known_ad_hosts_cache
    payload = load_adsense_signals_payload()
    hosts = payload.get("signals", {}).get("network_hosts", [])
    if not isinstance(hosts, list):
        _known_ad_hosts_cache = set()
    else:
        _known_ad_hosts_cache = {str(h).strip().lower() for h in hosts[:max(0, int(limit))] if str(h).strip()}
    return _known_ad_hosts_cache


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

    chain_domains = [extract_domain(url) for url in redirect_chain]
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
    """Compute confidence score in [0, 1] for ad click validity.

    Success means navigation happened — either a new tab opened or the page
    navigated to an external domain.  Both are equally valid; different ad
    providers use different mechanisms.
    """
    # New tab opened — success regardless of parent page URL
    if outcome_type == "new_tab_navigation":
        return 0.80

    # Same-tab navigation to an external domain — success
    if outcome_type == "same_tab_navigation":
        source_domain = extract_domain(source_url)
        final_domain = extract_domain(final_url)
        if final_domain and final_domain != source_domain:
            return 0.80
        # Navigated but stayed on same domain — internal link, not an ad click
        return 0.20

    # No navigation at all — click didn't work
    return 0.0


async def evaluate_ad_click_outcome(page, context,
                                    source_url: str,
                                    source_domain: str,
                                    tabs_before: int,
                                    max_wait_seconds: float = 8.0) -> dict:
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

    # Event-driven monitoring: poll for navigation, add tail buffer once detected
    poll_ms = 350
    ceiling_ms = int(max(1.0, max_wait_seconds) * 1000)
    elapsed_ms = 0
    try:
        while elapsed_ms < ceiling_ms:
            await page.wait_for_timeout(poll_ms)
            elapsed_ms += poll_ms

            tabs_now = len(context.pages)
            try:
                current_url = page.url or ""
            except Exception:
                current_url = ""

            if tabs_now > tabs_before or (current_url and current_url != source_url):
                # Navigation detected — tail buffer for redirect chains to settle
                tail_ms = random.randint(1000, 3000)
                await page.wait_for_timeout(tail_ms)
                elapsed_ms += tail_ms
                break
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

    final_domain = extract_domain(final_url)
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
            "monitor_ceiling_ms": ceiling_ms,
            "actual_elapsed_ms": elapsed_ms,
        },
    }
