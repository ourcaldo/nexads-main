"""
app/navigation/facebook.py
Facebook referrer: fbclid generation and direct header-based navigation.
"""

import random
import asyncio
import base64

from app.core.timings import timing_seconds


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


async def navigate_facebook_referrer(page, target_url: str, worker_id: int,
                                     is_mobile: bool = False) -> bool:
    """Navigate to target with Facebook referer header and fbclid parameter.

    Option 2: Set Referer header, navigate to target?fbclid=<generated>, clear header.
    """
    domain = "lm.facebook.com" if is_mobile else "l.facebook.com"
    referer = f"https://{domain}/"

    print(f"Worker {worker_id}: Using Facebook referer ({domain})")

    try:
        fbclid = generate_fbclid()
        separator = "&" if "?" in target_url else "?"
        url_with_fbclid = f"{target_url}{separator}fbclid={fbclid}"

        await page.set_extra_http_headers({"referer": referer})
        await page.goto(url_with_fbclid, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(timing_seconds("referrer_settle"))
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
