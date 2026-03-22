"""
nexads/navigation/referrer.py
Referrer handling: organic search, Google cookie acceptance, GDPR consent,
request interception, keyword selection, and social referrer generation.
"""

import random
import asyncio
import json
import pathlib
import string
import base64

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


def build_facebook_referrer(target_url: str, is_mobile: bool = False) -> dict:
    """Build a Facebook social referrer for the given target URL.

    Returns a dict with:
      - referer: origin-only Facebook referer header value
      - url: target URL with fbclid appended
    """
    if is_mobile:
        referer = "https://lm.facebook.com/"
    else:
        referer = "https://l.facebook.com/"

    fbclid = generate_fbclid()
    separator = "&" if "?" in target_url else "?"
    url_with_fbclid = f"{target_url}{separator}fbclid={fbclid}"

    return {"referer": referer, "url": url_with_fbclid}


def get_social_referrer(target_url: str = "", is_mobile: bool = False) -> dict:
    """Pick a random social referrer from referrers.json.

    Returns a dict with:
      - referer: the referrer header value (origin-only for platforms that use it)
      - url: the target URL (possibly with tracking params like fbclid)
      - platform: the platform name (e.g. "Facebook", "Twitter")
    """
    try:
        with open(_REFERRERS_PATH, 'r') as f:
            referrers = json.load(f)

        platforms = list(referrers['social'].keys())
        platform = random.choice(platforms)

        if platform == "Facebook":
            fb = build_facebook_referrer(target_url, is_mobile)
            return {"referer": fb["referer"], "url": fb["url"], "platform": platform}

        # For non-Facebook platforms, use simple origin-only referer
        urls = referrers['social'][platform]
        referer_url = random.choice(urls)
        if not referer_url.startswith('http://') and not referer_url.startswith('https://'):
            referer_url = f"https://{referer_url}"

        return {"referer": referer_url, "url": target_url, "platform": platform}

    except Exception as e:
        print(f"Error loading referrers: {str(e)}")
        return {"referer": "", "url": target_url, "platform": "unknown"}
