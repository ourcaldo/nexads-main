"""
app/navigation/facebook.py
Facebook referrer: fbclid generation, l.facebook.com link shim redirect,
and interstitial handling.
"""

import random
import asyncio
import json
import base64
import pathlib
from urllib.parse import quote

_REFERRERS_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "referrers.json"


def _random_base64url(length: int) -> str:
    """Generate a random base64url string of approximately the given length."""
    num_bytes = (length * 3) // 4 + 1
    raw = bytes(random.getrandbits(8) for _ in range(num_bytes))
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return encoded[:length]


def generate_fbclid() -> str:
    """Generate a realistic Facebook Click ID.

    Format: Iw + ~120 chars base64url + _aem_ + ~20 chars base64url
    Real fbclids are opaque encrypted blobs; no external party validates them.
    """
    body = _random_base64url(random.randint(115, 130))
    suffix = _random_base64url(random.randint(18, 26))
    return f"Iw{body}_aem_{suffix}"


def build_facebook_redirect_url(target_url: str, is_mobile: bool = False) -> str:
    """Build a full l.facebook.com/l.php redirect URL with fbclid baked into u param."""
    try:
        with open(_REFERRERS_PATH, 'r') as f:
            referrers = json.load(f)
        h_tokens = referrers['social']['Facebook']['h_tokens']
        h = random.choice(h_tokens)
    except Exception:
        h = ""

    fbclid = generate_fbclid()
    separator = "&" if "?" in target_url else "?"
    target_with_fbclid = f"{target_url}{separator}fbclid={fbclid}"
    encoded_target = quote(target_with_fbclid, safe="")

    domain = "lm.facebook.com" if is_mobile else "l.facebook.com"

    return f"https://{domain}/l.php?u={encoded_target}&h={h}"


def _extract_target_domain(target_url: str) -> str:
    """Extract the domain from a target URL for matching."""
    return target_url.split("//")[-1].split("/")[0]


def _ensure_fbclid(url: str) -> str:
    """Append a generated fbclid to URL if not already present."""
    if "fbclid=" in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}fbclid={generate_fbclid()}"


async def navigate_facebook_referrer(page, target_url: str, worker_id: int,
                                     is_mobile: bool = False) -> bool:
    """Navigate to target URL with Facebook referer header set directly.

    Sets Referer: https://l.facebook.com/ via extra HTTP headers, navigates
    to the target, then clears the header. No l.facebook.com visit — Camoufox
    can't preserve the referer through Facebook's interstitial.
    """
    domain = "lm.facebook.com" if is_mobile else "l.facebook.com"
    referer = f"https://{domain}/"

    print(f"Worker {worker_id}: Using Facebook referer ({domain})")

    try:
        await page.set_extra_http_headers({"referer": referer})
        await page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.5, 3.0))
        await page.set_extra_http_headers({})

        print(f"Worker {worker_id}: Navigated with Facebook referer: {page.url}")
        return True

    except Exception as e:
        print(f"Worker {worker_id}: Facebook referrer navigation error: {str(e)}")
        try:
            await page.set_extra_http_headers({})
        except Exception:
            pass
        return False
