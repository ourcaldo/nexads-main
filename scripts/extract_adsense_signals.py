"""
Build AdSense-related detection signals from EasyList-like filter files.

Usage examples:
  python scripts/extract_adsense_signals.py
  python scripts/extract_adsense_signals.py --source easylist.txt --output data/adsense_signals.json
"""

from __future__ import annotations

import argparse
import pathlib
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ads.signals import DEFAULT_OUTPUT, DEFAULT_SOURCE, update_adsense_signals


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract AdSense-like detection signals from EasyList-style filters."
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="EasyList URL or local file path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument("--timeout", type=int, default=30, help="Download timeout in seconds")
    args = parser.parse_args()

    output_path = pathlib.Path(args.output)
    payload = update_adsense_signals(
        source=args.source,
        output_path=output_path,
        timeout_seconds=args.timeout,
    )

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
