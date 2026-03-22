"""
app/navigation/referrer.py
Social referrer dispatch: picks a random platform from referrers.json
and delegates to the appropriate handler.

Re-exports organic search and Facebook functions for backward compatibility.
"""

import random
import json
import pathlib

from app.navigation.organic import (  # noqa: F401
    get_random_keyword,
    perform_organic_search,
    accept_google_cookies,
    handle_gdpr_consent,
)
from app.navigation.facebook import navigate_facebook_referrer  # noqa: F401

_REFERRERS_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "referrers.json"


def get_social_referrer(target_url: str = "", is_mobile: bool = False) -> dict:
    """Pick a random social referrer from referrers.json.

    Returns a dict with:
      - platform: the platform name (e.g. "Facebook", "Twitter")
      - navigate_fn: True if platform uses async navigation (Facebook), False for header-only
      - referer: the referrer header value (for non-Facebook platforms)
      - url: the target URL (for non-Facebook platforms)
    """
    try:
        with open(_REFERRERS_PATH, 'r') as f:
            referrers = json.load(f)

        platforms = list(referrers['social'].keys())
        platform = random.choice(platforms)

        if platform == "Facebook":
            return {"platform": platform, "navigate_fn": True,
                    "referer": "", "url": target_url}

        # For non-Facebook platforms, use simple origin-only referer
        social_data = referrers['social'][platform]
        if isinstance(social_data, list):
            urls = social_data
        elif isinstance(social_data, dict):
            urls = social_data.get("urls", [])
        else:
            urls = []

        referer_url = random.choice(urls) if urls else ""
        if referer_url and not referer_url.startswith('http://') and not referer_url.startswith('https://'):
            referer_url = f"https://{referer_url}"

        return {"platform": platform, "navigate_fn": False,
                "referer": referer_url, "url": target_url}

    except Exception as e:
        print(f"Error loading referrers: {str(e)}")
        return {"platform": "unknown", "navigate_fn": False,
                "referer": "", "url": target_url}
