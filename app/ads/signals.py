"""
nexads/ads/signals.py
EasyList-derived AdSense signal loading and refresh helpers.
"""

from __future__ import annotations

import json
import pathlib
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

_PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DEFAULT_SOURCE = "https://easylist.to/easylist/easylist.txt"
DEFAULT_OUTPUT = _PKG_ROOT / "data" / "adsense_signals.json"
KEYWORDS = (
    "adsbygoogle",
    "googleads",
    "doubleclick",
    "googlesyndication",
    "adservice.google",
    "g.doubleclick",
    "adsense",
)


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def load_source(source: str, timeout_seconds: int = 30) -> str:
    """Load filter list content from URL or local file path."""
    if _is_url(source):
        request = urllib.request.Request(
            source,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; nexads-signal-extractor/1.0)",
                "Accept": "text/plain,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return response.read().decode("utf-8", errors="replace")

    path = pathlib.Path(source)
    return path.read_text(encoding="utf-8", errors="replace")


def _contains_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in KEYWORDS)


def _normalize_host(candidate: str) -> str:
    host = candidate.strip().lower()
    host = host.split("^")[0]
    host = host.split("/")[0]
    host = host.split("$")[0]
    host = host.strip("|")
    return host


def _extract_domain_specific_host(rule_line: str) -> str | None:
    if not rule_line.startswith("||"):
        return None

    host_candidate = _normalize_host(rule_line[2:])
    if not host_candidate or "." not in host_candidate:
        return None

    return host_candidate


def _extract_url_prefix_host(rule_line: str) -> str | None:
    if not (rule_line.startswith("|http://") or rule_line.startswith("|https://")):
        return None

    parsed = urllib.parse.urlparse(rule_line[1:])
    if parsed.netloc and "." in parsed.netloc:
        return parsed.netloc.lower()

    return None


def _looks_like_css_selector(selector: str) -> bool:
    """Return True for selectors likely supported by Playwright query_selector_all."""
    s = selector.strip()
    if not s:
        return False

    # Skip scriptlets/extended syntaxes that are not DOM selectors.
    blocked_fragments = (
        "+js(",
        "script:inject(",
        "script:contains(",
        "removeparam=",
        "redirect=",
        "$",
    )
    if any(fragment in s for fragment in blocked_fragments):
        return False

    if s.startswith("/"):
        return False

    return True


def extract_signals(content: str) -> dict:
    """Extract candidate AdSense-related selectors and domains."""
    selectors: set[str] = set()
    network_hosts: set[str] = set()
    url_prefix_hosts: set[str] = set()
    sample_rules: set[str] = set()

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("!") or line.startswith("["):
            continue

        if not _contains_keyword(line):
            continue

        if "##" in line or "#@#" in line:
            sep = "##" if "##" in line else "#@#"
            try:
                _, selector = line.split(sep, 1)
            except ValueError:
                selector = line
            selector = selector.strip()
            if selector and _looks_like_css_selector(selector):
                selectors.add(selector)
                sample_rules.add(line)
            continue

        host = _extract_domain_specific_host(line)
        if host:
            network_hosts.add(host)
            sample_rules.add(line)
            continue

        host = _extract_url_prefix_host(line)
        if host:
            url_prefix_hosts.add(host)
            sample_rules.add(line)
            continue

        sample_rules.add(line)

    return {
        "keywords": list(KEYWORDS),
        "cosmetic_selectors": sorted(selectors),
        "network_hosts": sorted(network_hosts),
        "url_prefix_hosts": sorted(url_prefix_hosts),
        "sample_rules": sorted(sample_rules)[:120],
    }


def build_payload(source: str, content: str) -> dict:
    """Build JSON payload for persisted AdSense signals."""
    signals = extract_signals(content)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "stats": {
            "cosmetic_selector_count": len(signals["cosmetic_selectors"]),
            "network_host_count": len(signals["network_hosts"]),
            "url_prefix_host_count": len(signals["url_prefix_hosts"]),
            "sample_rule_count": len(signals["sample_rules"]),
        },
        "signals": signals,
    }


def write_payload(payload: dict, output_path: pathlib.Path | str = DEFAULT_OUTPUT) -> pathlib.Path:
    """Write signal payload to disk and return output path."""
    out_path = pathlib.Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def update_adsense_signals(source: str = DEFAULT_SOURCE,
                           output_path: pathlib.Path | str = DEFAULT_OUTPUT,
                           timeout_seconds: int = 30) -> dict:
    """Download/parse source list and write refreshed AdSense signals payload."""
    content = load_source(source, timeout_seconds=timeout_seconds)
    payload = build_payload(source, content)
    write_payload(payload, output_path)
    return payload


def load_adsense_signals_payload(output_path: pathlib.Path | str = DEFAULT_OUTPUT) -> dict:
    """Load persisted AdSense signal payload from disk."""
    out_path = pathlib.Path(output_path)
    if not out_path.exists():
        return {}

    try:
        with out_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def ensure_adsense_signals_updated(force: bool = False,
                                   max_age_days: int = 7,
                                   source: str = DEFAULT_SOURCE,
                                   output_path: pathlib.Path | str = DEFAULT_OUTPUT,
                                   timeout_seconds: int = 30) -> tuple[bool, str]:
    """Ensure signals exist and refresh when missing/stale/invalid.

    Returns tuple `(updated, message)`.
    """
    out_path = pathlib.Path(output_path)
    if force or not out_path.exists():
        payload = update_adsense_signals(source, out_path, timeout_seconds)
        return True, (
            f"Signals refreshed ({payload['stats']['cosmetic_selector_count']} selectors, "
            f"{payload['stats']['network_host_count']} hosts)"
        )

    payload = load_adsense_signals_payload(out_path)
    generated_at = payload.get("generated_at_utc")
    if not generated_at:
        payload = update_adsense_signals(source, out_path, timeout_seconds)
        return True, "Signals refreshed (missing timestamp)"

    try:
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except Exception:
        payload = update_adsense_signals(source, out_path, timeout_seconds)
        return True, "Signals refreshed (invalid timestamp)"

    if datetime.now(timezone.utc) - generated > timedelta(days=max_age_days):
        payload = update_adsense_signals(source, out_path, timeout_seconds)
        return True, "Signals refreshed (stale cache)"

    return False, "Signals cache is current"


def load_adsense_cosmetic_selectors(output_path: pathlib.Path | str = DEFAULT_OUTPUT,
                                    limit: int = 220) -> list[str]:
    """Load persisted cosmetic selectors with optional cap for runtime performance."""
    payload = load_adsense_signals_payload(output_path)
    selectors = payload.get("signals", {}).get("cosmetic_selectors", [])
    if not isinstance(selectors, list):
        return []

    clean = [s for s in selectors if isinstance(s, str) and s.strip()]
    return clean[:max(0, int(limit))]
