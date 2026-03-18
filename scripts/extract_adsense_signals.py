"""
Build AdSense-related detection signals from EasyList-like filter files.

Usage examples:
  python scripts/extract_adsense_signals.py
  python scripts/extract_adsense_signals.py --source easylist.txt --output data/adsense_signals.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DEFAULT_SOURCE = "https://easylist.to/easylist/easylist.txt"
DEFAULT_OUTPUT = pathlib.Path("data/adsense_signals.json")
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
    # network rules usually look like: ||example.com^ or ||example.com/path
    if not rule_line.startswith("||"):
        return None

    host_candidate = _normalize_host(rule_line[2:])
    if not host_candidate or "." not in host_candidate:
        return None

    return host_candidate


def _extract_url_prefix_host(rule_line: str) -> str | None:
    # handles patterns like |https://adclick.g.doubleclick.net/
    if not (rule_line.startswith("|http://") or rule_line.startswith("|https://")):
        return None

    parsed = urllib.parse.urlparse(rule_line[1:])
    if parsed.netloc and "." in parsed.netloc:
        return parsed.netloc.lower()

    return None


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

        # Cosmetic filters.
        if "##" in line or "#@#" in line:
            sep = "##" if "##" in line else "#@#"
            try:
                _, selector = line.split(sep, 1)
            except ValueError:
                selector = line
            selector = selector.strip()
            if selector:
                selectors.add(selector)
                sample_rules.add(line)
            continue

        # Network filters.
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

        # Keep a few additional interesting lines as samples.
        sample_rules.add(line)

    return {
        "keywords": list(KEYWORDS),
        "cosmetic_selectors": sorted(selectors),
        "network_hosts": sorted(network_hosts),
        "url_prefix_hosts": sorted(url_prefix_hosts),
        "sample_rules": sorted(sample_rules)[:120],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract AdSense-like detection signals from EasyList-style filters."
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="EasyList URL or local file path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument("--timeout", type=int, default=30, help="Download timeout in seconds")
    args = parser.parse_args()

    content = load_source(args.source, timeout_seconds=args.timeout)
    signals = extract_signals(content)

    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": args.source,
        "stats": {
            "cosmetic_selector_count": len(signals["cosmetic_selectors"]),
            "network_host_count": len(signals["network_hosts"]),
            "url_prefix_host_count": len(signals["url_prefix_hosts"]),
            "sample_rule_count": len(signals["sample_rules"]),
        },
        "signals": signals,
    }

    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote AdSense signals to {output_path}")
    print(
        "Summary: selectors={0}, network_hosts={1}, url_prefix_hosts={2}".format(
            payload["stats"]["cosmetic_selector_count"],
            payload["stats"]["network_host_count"],
            payload["stats"]["url_prefix_host_count"],
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
