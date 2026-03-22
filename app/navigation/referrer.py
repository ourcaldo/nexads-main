"""
nexads/navigation/referrer.py
Referrer handling: organic search, Google cookie acceptance, GDPR consent,
request interception, keyword selection, and social referrer generation.
"""

import random
import asyncio
import json
import pathlib
import base64
from urllib.parse import quote

from app.browser.humanization import gaussian_ms
from app.navigation.consent import handle_consent_dialog

_REFERRERS_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "referrers.json"

try:
    from humantyping import HumanTyper

    _HUMANTYPING_AVAILABLE = True
except Exception:
    HumanTyper = None
    _HUMANTYPING_AVAILABLE = False


async def _human_type_keyword(search_input, keyword: str):
    """Type keyword using humantyping Markov model (with fallback)."""
    if _HUMANTYPING_AVAILABLE and HumanTyper is not None:
        try:
            # Session-level typing cadence naturally varies among users.
            wpm = max(35.0, min(95.0, random.gauss(64.0, 9.0)))
            typer = HumanTyper(wpm=wpm, layout="qwerty")
            await typer.type(search_input, keyword)
            return
        except Exception as e:
            print(f"HumanTyping fallback triggered: {str(e)}")

    # Fallback path if package is missing or runtime typing fails.
    await search_input.type(keyword, delay=gaussian_ms(90, 24, 35, 220))


async def setup_request_interceptor(page):
    """Block Google login pages via request interception. Returns the handler so it can be removed."""
    async def _handler(route):
        if "accounts.google.com" in route.request.url:
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", _handler)
    return _handler


async def accept_google_cookies(page):
    """Auto-accept Google cookie consent popup if present."""
    try:
        accept_selectors = [
            "button:has-text('Accept all'), button:has-text('I agree'), button:has-text('Accept')",
            "button#L2AGLb",
            "div[role='dialog'] button:has-text('Accept')"
        ]
        for selector in accept_selectors:
            try:
                accept_button = await page.query_selector(selector)
                if accept_button and await accept_button.is_visible():
                    await accept_button.click(timeout=7500)
                    print("Accepted Google cookies")
                    return True
            except:
                continue
        return False
    except Exception as e:
        print(f"Error accepting cookies: {str(e)}")
        return False


async def handle_gdpr_consent(page, worker_id: int):
    """Backward-compatible wrapper for universal consent handler."""
    result = await handle_consent_dialog(page, worker_id, max_wait_seconds=12)
    return result.get("status") == "resolved"


def get_random_keyword(config: dict):
    """Return a random organic search keyword from config, or None if unavailable."""
    if "organic" not in config['referrer']['types']:
        return None

    keywords = config['referrer']['organic_keywords']

    if isinstance(keywords, list):
        valid_keywords = [k.strip() for k in keywords if k and str(k).strip()]
    elif isinstance(keywords, str):
        keyword_str = keywords.replace('\n', ',').strip()
        valid_keywords = [k.strip() for k in keyword_str.split(',') if k.strip()]
    else:
        valid_keywords = [str(keywords).strip()] if str(keywords).strip() else []

    if len(valid_keywords) == 1:
        return valid_keywords[0]
    if valid_keywords:
        return random.choice(valid_keywords)

    return None


async def perform_organic_search(page, keyword: str, target_domain: str,
                                 worker_id: int, config: dict, extract_domain_fn):
    """Perform a real Google search and click the first result matching the target domain."""
    max_retries = 3
    retry_count = 0
    main_domain = target_domain.removeprefix('www.').split('/')[0]

    interceptor_handler = await setup_request_interceptor(page)

    try:
        while retry_count < max_retries:
            try:
                print(f"Worker {worker_id}: Performing organic search - visiting Google")
                await page.goto("https://www.google.com/", timeout=30000, wait_until="domcontentloaded")

                if config['browser']['auto_accept_cookies']:
                    await accept_google_cookies(page)

                print(f"Worker {worker_id}: Searching for keyword: {keyword}")
                search_input = await page.wait_for_selector(
                    'textarea[name="q"], input[name="q"]', state="visible", timeout=45000)

                if not search_input:
                    print(f"Worker {worker_id}: Could not find search input")
                    return False

                await search_input.click(click_count=3)
                await search_input.press("Backspace")

                await _human_type_keyword(search_input, keyword)

                await search_input.press("Enter")
                await page.wait_for_load_state("networkidle", timeout=45000)
                print(f"Worker {worker_id}: Looking for {main_domain} in results")

                await page.wait_for_selector('div#search', state="visible", timeout=45000)

                all_links = await page.query_selector_all('a[href]')
                if not all_links:
                    print(f"Worker {worker_id}: No links found in search results")
                    return False

                target_link = None
                for link in all_links:
                    try:
                        href = await link.get_attribute('href')
                        if href and main_domain in extract_domain_fn(href):
                            target_link = link
                            break
                    except:
                        continue

                if not target_link:
                    print(f"Worker {worker_id}: No links found matching main domain")
                    return False

                await target_link.scroll_into_view_if_needed()
                await page.wait_for_timeout(gaussian_ms(900, 260, 350, 2200))

                async with page.expect_navigation(timeout=45000):
                    await target_link.click(delay=gaussian_ms(110, 30, 45, 220))

                await page.wait_for_load_state("networkidle", timeout=45000)

                current_main_domain = extract_domain_fn(page.url)
                if main_domain not in current_main_domain:
                    print(f"Worker {worker_id}: Navigation failed. Current: {current_main_domain}, Expected: {main_domain}")
                    await page.go_back(timeout=45000)
                    await page.wait_for_load_state("networkidle")
                    retry_count += 1
                    continue

                print(f"Worker {worker_id}: Successfully navigated to domain: {page.url}")
                return True

            except Exception as e:
                print(f"Worker {worker_id}: Organic search error (attempt {retry_count + 1}): {str(e)}")
                retry_count += 1
                if retry_count < max_retries:
                    await page.wait_for_timeout(gaussian_ms(2100, 280, 1300, 3200))
                continue

        print(f"Worker {worker_id}: Max retries reached for organic search")
        return False

    finally:
        try:
            await page.unroute("**/*", interceptor_handler)
        except Exception:
            pass


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


async def navigate_facebook_referrer(page, target_url: str, worker_id: int,
                                     is_mobile: bool = False) -> bool:
    """Navigate through Facebook's l.facebook.com link shim to reach target URL.

    Handles the "Leaving Facebook" interstitial by detecting and clicking through it.
    Falls back to header-based approach if the redirect fails.
    """
    redirect_url = build_facebook_redirect_url(target_url, is_mobile)
    domain = "lm.facebook.com" if is_mobile else "l.facebook.com"

    print(f"Worker {worker_id}: Navigating through {domain} link shim")

    try:
        await page.goto(redirect_url, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.5, 3.0))

        current_url = page.url

        # --- Check if we landed on the target already ---
        if target_url.split("//")[-1].split("/")[0] in current_url:
            print(f"Worker {worker_id}: Facebook redirect succeeded directly: {current_url}")
            return True

        # --- Handle "Leaving Facebook" interstitial ---
        if "facebook.com" in current_url:
            print(f"Worker {worker_id}: Hit Facebook interstitial, attempting to click through")

            # Try multiple selectors for the "follow link" / "continue" button
            interstitial_selectors = [
                'a[href*="' + target_url.split("//")[-1].split("/")[0] + '"]',
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
                        print(f"Worker {worker_id}: Found interstitial link: {selector}")
                        await link.click(timeout=10000)
                        await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        await asyncio.sleep(random.uniform(1.0, 2.0))

                        if target_url.split("//")[-1].split("/")[0] in page.url:
                            print(f"Worker {worker_id}: Successfully clicked through interstitial: {page.url}")
                            return True
                except Exception:
                    continue

            # Last resort: try clicking any visible link on the page
            try:
                all_links = await page.query_selector_all("a[href]:visible")
                for link in all_links:
                    try:
                        href = await link.get_attribute("href")
                        if href and target_url.split("//")[-1].split("/")[0] in href:
                            await link.click(timeout=10000)
                            await page.wait_for_load_state("domcontentloaded", timeout=15000)
                            await asyncio.sleep(1)
                            if target_url.split("//")[-1].split("/")[0] in page.url:
                                print(f"Worker {worker_id}: Clicked through via href match: {page.url}")
                                return True
                    except Exception:
                        continue
            except Exception:
                pass

        # --- Fallback: header-based approach ---
        print(f"Worker {worker_id}: Facebook redirect failed, falling back to header approach")
        referer = f"https://{domain}/"
        fbclid = generate_fbclid()
        separator = "&" if "?" in target_url else "?"
        fallback_url = f"{target_url}{separator}fbclid={fbclid}"

        await page.set_extra_http_headers({"referer": referer})
        await page.goto(fallback_url, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.5, 3.0))
        await page.set_extra_http_headers({})
        print(f"Worker {worker_id}: Fallback header approach used: {page.url}")
        return True

    except Exception as e:
        print(f"Worker {worker_id}: Facebook referrer navigation error: {str(e)}")
        return False


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
