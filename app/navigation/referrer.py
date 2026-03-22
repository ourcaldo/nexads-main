"""
app/navigation/referrer.py
Social referrer dispatch: picks a random platform from referrers.json
and delegates to the appropriate handler.

Re-exports organic search functions for backward compatibility.
"""

import random
import asyncio
import json
import pathlib

from app.navigation.organic import (  # noqa: F401
    get_random_keyword,
    perform_organic_search,
    accept_google_cookies,
    handle_gdpr_consent,
    warm_google_profile,
)
from app.navigation.facebook import navigate_facebook_referrer
from app.navigation.instagram import navigate_instagram_referrer

_REFERRERS_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "referrers.json"

# Platforms with dedicated navigation handlers (set referer + add tracking params)
_PLATFORM_HANDLERS = {
    "Facebook": navigate_facebook_referrer,
    "Instagram": navigate_instagram_referrer,
}


def get_social_referrer(target_url: str = "", is_mobile: bool = False) -> dict:
    """Pick a random social referrer from referrers.json.

    Returns a dict with:
      - platform: the platform name (e.g. "Facebook", "Twitter")
      - has_handler: True if platform has a dedicated async navigation handler
      - referer: the referrer header value (for platforms without handlers)
      - url: the target URL
    """
    try:
        with open(_REFERRERS_PATH, 'r') as f:
            referrers = json.load(f)

        platforms = list(referrers['social'].keys())
        platform = random.choice(platforms)

        if platform in _PLATFORM_HANDLERS:
            return {"platform": platform, "has_handler": True,
                    "referer": "", "url": target_url}

        # For platforms without handlers, use simple header-based referer
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

        return {"platform": platform, "has_handler": False,
                "referer": referer_url, "url": target_url}

    except Exception as e:
        print(f"Error loading referrers: {str(e)}")
        return {"platform": "unknown", "has_handler": False,
                "referer": "", "url": target_url}


async def navigate_social_referrer(page, target_url: str, worker_id: int,
                                   is_mobile: bool = False) -> bool:
    """Pick a random social platform and navigate to target with appropriate referer.

    Dispatches to platform-specific handlers (Facebook, Instagram) or falls back
    to generic header-based approach for other platforms.
    """
    social = get_social_referrer(target_url, is_mobile)
    platform = social["platform"]

    print(f"Worker {worker_id}: Using {platform} social referrer")

    if platform in _PLATFORM_HANDLERS:
        return await _PLATFORM_HANDLERS[platform](page, target_url, worker_id, is_mobile)

    # Generic header-based approach for other platforms
    try:
        if social["referer"]:
            await page.set_extra_http_headers({"referer": social["referer"]})
        await page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.5, 3.0))
        await page.set_extra_http_headers({})

        print(f"Worker {worker_id}: Navigated with {platform} referer: {page.url}")
        return True

    except Exception as e:
        print(f"Worker {worker_id}: {platform} referrer navigation error: {str(e)}")
        try:
            await page.set_extra_http_headers({})
        except Exception:
            pass
        return False
