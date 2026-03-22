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


async def navigate_facebook_referrer(page, target_url: str, worker_id: int,
                                     is_mobile: bool = False) -> bool:
    """Navigate through Facebook's l.facebook.com link shim to reach target URL.

    Visits l.facebook.com first (realistic browser history), then navigates to
    the target with an explicit referer header. Facebook's interstitial strips
    the Referer via rel="noreferrer", so we extract the destination and navigate
    with Playwright's referer param to preserve it.
    """
    redirect_url = build_facebook_redirect_url(target_url, is_mobile)
    domain = "lm.facebook.com" if is_mobile else "l.facebook.com"
    referer = f"https://{domain}/"
    target_domain = _extract_target_domain(target_url)

    print(f"Worker {worker_id}: Navigating through {domain} link shim")

    try:
        await page.goto(redirect_url, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.5, 3.0))

        current_url = page.url

        # --- Check if we landed on the target already (302 redirect worked) ---
        if target_domain in current_url:
            print(f"Worker {worker_id}: Facebook redirect succeeded directly: {current_url}")
            return True

        # --- Handle "Leaving Facebook" interstitial ---
        # Instead of clicking (which strips referer via rel="noreferrer"),
        # extract the destination URL and navigate with explicit referer.
        if "facebook.com" in current_url:
            print(f"Worker {worker_id}: Hit Facebook interstitial, extracting destination")

            destination_url = None
            interstitial_selectors = [
                f'a[href*="{target_domain}"]',
                'a:has-text("Follow Link")',
                'a:has-text("follow link")',
                'a:has-text("Continue")',
                'a:has-text("continue")',
                '#u_0_0_yS',
                'a[role="button"]',
                'div[role="main"] a[href]',
            ]

            for selector in interstitial_selectors:
                try:
                    link = await page.query_selector(selector)
                    if link and await link.is_visible():
                        href = await link.get_attribute("href")
                        if href and target_domain in href:
                            destination_url = href
                            print(f"Worker {worker_id}: Found destination in interstitial: {selector}")
                            break
                except Exception:
                    continue

            # Last resort: scan all visible links for target domain
            if not destination_url:
                try:
                    all_links = await page.query_selector_all("a[href]:visible")
                    for link in all_links:
                        try:
                            href = await link.get_attribute("href")
                            if href and target_domain in href:
                                destination_url = href
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

            if destination_url:
                print(f"Worker {worker_id}: Navigating to target with Facebook referer")
                await page.goto(destination_url, timeout=30000,
                                wait_until="domcontentloaded", referer=referer)
                await asyncio.sleep(random.uniform(1.5, 3.0))
                if target_domain in page.url:
                    print(f"Worker {worker_id}: Successfully reached target via interstitial: {page.url}")
                    return True

        # --- Fallback: direct navigation with referer ---
        print(f"Worker {worker_id}: Using direct navigation with Facebook referer")
        fbclid = generate_fbclid()
        separator = "&" if "?" in target_url else "?"
        fallback_url = f"{target_url}{separator}fbclid={fbclid}"

        await page.goto(fallback_url, timeout=30000,
                        wait_until="domcontentloaded", referer=referer)
        await asyncio.sleep(random.uniform(1.5, 3.0))
        print(f"Worker {worker_id}: Fallback with referer used: {page.url}")
        return True

    except Exception as e:
        print(f"Worker {worker_id}: Facebook referrer navigation error: {str(e)}")
        return False
