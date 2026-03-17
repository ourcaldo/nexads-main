"""
nexads/navigation/referrer.py
Referrer handling: organic search, Google cookie acceptance, GDPR consent,
request interception, and keyword selection.
"""

import random
import asyncio
import json
import pathlib

_REFERRERS_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "referrers.json"


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
    """Handle GDPR consent popup if present. Returns True if handled."""
    try:
        gdpr_selectors = [
            'div.fc-dialog-container',
            'div[class*="cookie"]',
            'div[class*="consent"]',
            'div[class*="gdpr"]',
            'div[class*="privacy"]'
        ]

        gdpr_dialog = None
        for selector in gdpr_selectors:
            try:
                gdpr_dialog = await page.query_selector(selector)
                if gdpr_dialog and await gdpr_dialog.is_visible():
                    print(f"Worker {worker_id}: GDPR consent dialog detected")
                    break
                gdpr_dialog = None
            except:
                continue

        if not gdpr_dialog:
            return False

        consent_selectors = [
            'p.fc-button-label:has-text("Consent")',
            'button:has-text("Consent")',
            'button:has-text("Accept")',
            'button:has-text("Agree")',
            'button:has-text("I agree")',
            'button#accept-cookies',
            'button#consent-button'
        ]

        consent_button = None
        for selector in consent_selectors:
            try:
                consent_button = await page.query_selector(selector)
                if consent_button and await consent_button.is_visible():
                    break
                consent_button = None
            except:
                continue

        if not consent_button:
            print(f"Worker {worker_id}: GDPR dialog found but no consent button detected")
            return False

        await consent_button.scroll_into_view_if_needed()
        box = await consent_button.bounding_box()
        if not box:
            return False

        await page.mouse.move(
            box['x'] + box['width'] / 2,
            box['y'] + box['height'] / 2,
            steps=random.randint(5, 10)
        )
        await page.wait_for_timeout(random.randint(300, 800))
        await consent_button.click(delay=random.randint(50, 200))
        print(f"Worker {worker_id}: Clicked GDPR consent button")

        try:
            await page.wait_for_selector(consent_selectors[0], state='hidden', timeout=5000)
        except:
            pass

        return True

    except Exception as e:
        print(f"Worker {worker_id}: Error handling GDPR consent: {str(e)}")
        return False


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

    print(f"DEBUG - Raw keyword data: {repr(keywords)}")
    return None


async def perform_organic_search(page, keyword: str, target_domain: str,
                                 worker_id: int, config: dict, extract_domain_fn):
    """Perform a real Google search and click the first result matching the target domain."""
    max_retries = 3
    retry_count = 0
    main_domain = target_domain.removeprefix('www.').split('/')[0]

    interceptor_handler = await setup_request_interceptor(page)

    while retry_count < max_retries:
        try:
            print(f"Worker {worker_id}: Performing organic search - visiting Google")
            await page.goto("https://www.google.com/", timeout=90000, wait_until="networkidle")

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

            # Use type() instead of press(char) loop — handles non-ASCII/unicode keywords
            await page.keyboard.type(keyword, delay=random.randint(50, 150))

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
            await page.wait_for_timeout(random.randint(500, 1500))

            async with page.expect_navigation(timeout=45000):
                await target_link.click(delay=random.randint(50, 200))

            await page.wait_for_load_state("networkidle", timeout=45000)

            current_main_domain = extract_domain_fn(page.url).replace('www.', '')
            if main_domain not in current_main_domain:
                print(f"Worker {worker_id}: Navigation failed. Current: {current_main_domain}, Expected: {main_domain}")
                await page.go_back(timeout=45000)
                await page.wait_for_load_state("networkidle")
                retry_count += 1
                continue

            print(f"Worker {worker_id}: Successfully navigated to domain: {page.url}")
            await page.unroute("**/*", interceptor_handler)
            return True

        except Exception as e:
            print(f"Worker {worker_id}: Organic search error (attempt {retry_count + 1}): {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                await page.wait_for_timeout(2000)
            continue

    print(f"Worker {worker_id}: Max retries reached for organic search")
    try:
        await page.unroute("**/*", interceptor_handler)
    except Exception:
        pass
    return False


def get_social_referrer() -> str:
    """Pick a random social referrer URL from referrers.json."""
    try:
        with open(_REFERRERS_PATH, 'r') as f:
            referrers = json.load(f)
        social = random.choice(list(referrers['social'].values()))
        url = random.choice(social)
        # Only prepend scheme if not already present
        if not url.startswith('http://') and not url.startswith('https://'):
            url = f"https://{url}"
        return url
    except Exception as e:
        print(f"Error loading referrers: {str(e)}")
        return ""
