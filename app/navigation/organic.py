"""
app/navigation/organic.py
Organic Google search: perform search, click matching result, cookie acceptance,
request interception, and human-like typing.
"""

import random
import asyncio
import time

from app.core.timings import timing_ms
from app.navigation.consent import handle_consent_dialog

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
    await search_input.type(keyword, delay=timing_ms("warmup_typing"))


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
                await page.wait_for_timeout(timing_ms("warmup_result_wait"))

                async with page.expect_navigation(timeout=45000):
                    await target_link.click(delay=timing_ms("warmup_click"))

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
                    await page.wait_for_timeout(timing_ms("warmup_page_dwell"))
                continue

        print(f"Worker {worker_id}: Max retries reached for organic search")
        return False

    finally:
        try:
            await page.unroute("**/*", interceptor_handler)
        except Exception:
            pass


async def warm_google_profile(page, worker_id: int, config: dict,
                              max_seconds: int = 60):
    """Browse Google briefly to acquire cookies and build a minimal profile.

    Searches multiple organic keywords quickly, clicks results, brief scroll,
    then returns with the page on Google ready for the next navigation step.
    """
    deadline = time.time() + max_seconds
    start = time.time()
    print(f"Worker {worker_id}: Starting Google profile warm-up ({max_seconds}s max)")

    interceptor_handler = await setup_request_interceptor(page)

    try:
        # --- Visit Google and accept cookies ---
        await page.goto(
            "https://www.google.com/", timeout=20000, wait_until="domcontentloaded"
        )
        await accept_google_cookies(page)
        await page.wait_for_timeout(timing_ms("warmup_settle"))

        # Pick keywords from the organic config
        all_keywords = []
        raw = config.get("referrer", {}).get("organic_keywords", [])
        if isinstance(raw, list):
            all_keywords = [k.strip() for k in raw if k and str(k).strip()]
        elif isinstance(raw, str):
            all_keywords = [k.strip() for k in raw.replace('\n', ',').split(',') if k.strip()]

        if not all_keywords:
            print(f"Worker {worker_id}: No organic keywords configured, skipping warm-up")
            return

        keywords = random.sample(all_keywords, min(len(all_keywords), 5))

        for kw in keywords:
            if time.time() >= deadline:
                break

            # --- Search ---
            try:
                search_input = await page.wait_for_selector(
                    'textarea[name="q"], input[name="q"]', state="visible", timeout=10000
                )
            except Exception:
                # Consent dialog may be blocking — try accepting and retry
                await accept_google_cookies(page)
                await page.wait_for_timeout(timing_ms("warmup_retry"))
                try:
                    search_input = await page.wait_for_selector(
                        'textarea[name="q"], input[name="q"]', state="visible", timeout=8000
                    )
                except Exception:
                    # Still blocked, try reloading Google
                    try:
                        await page.goto(
                            "https://www.google.com/", timeout=15000,
                            wait_until="domcontentloaded",
                        )
                        await accept_google_cookies(page)
                        await page.wait_for_timeout(timing_ms("warmup_retry"))
                        search_input = await page.wait_for_selector(
                            'textarea[name="q"], input[name="q"]', state="visible", timeout=8000
                        )
                    except Exception:
                        print(f"Worker {worker_id}: Cannot find Google search input, ending warm-up")
                        break
            if not search_input:
                break

            await search_input.click(click_count=3)
            await search_input.press("Backspace")
            await _human_type_keyword(search_input, kw)
            await search_input.press("Enter")

            try:
                await page.wait_for_load_state("domcontentloaded", timeout=12000)
            except Exception:
                pass

            if time.time() >= deadline:
                break

            # --- Scroll the search results briefly ---
            try:
                await page.wait_for_selector("div#search", state="visible", timeout=8000)
                await page.mouse.wheel(0, random.randint(200, 400))
                await page.wait_for_timeout(timing_ms("warmup_scroll_gap"))
            except Exception:
                continue

            # --- Click a random organic result ---
            links = await page.query_selector_all("div#search a[href]")
            clickable = []
            for link in links:
                try:
                    href = await link.get_attribute("href")
                    if href and href.startswith("http") and "google." not in href:
                        if await link.is_visible():
                            clickable.append(link)
                except Exception:
                    continue

            if not clickable:
                # No results to click, move to next keyword
                continue

            target = random.choice(clickable[:5])
            try:
                await target.scroll_into_view_if_needed()
                await page.wait_for_timeout(timing_ms("warmup_result_wait"))
                await target.click(delay=timing_ms("warmup_click"))
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass

            if time.time() >= deadline:
                break

            # --- Quick scroll on the result page, then go back ---
            try:
                await page.mouse.wheel(0, random.randint(150, 400))
                await page.wait_for_timeout(timing_ms("warmup_scroll_gap"))
            except Exception:
                pass

            # --- Go back to Google for next keyword ---
            try:
                await page.go_back(timeout=10000)
                await page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                try:
                    await page.goto(
                        "https://www.google.com/", timeout=10000,
                        wait_until="domcontentloaded",
                    )
                except Exception:
                    break

        # --- Ensure we end on Google so session navigation flows naturally ---
        try:
            current = page.url or ""
            if "google." not in current:
                await page.goto(
                    "https://www.google.com/", timeout=10000,
                    wait_until="domcontentloaded",
                )
        except Exception:
            pass

        elapsed = time.time() - start
        print(f"Worker {worker_id}: Google warm-up complete ({elapsed:.1f}s)")

    except Exception as e:
        print(f"Worker {worker_id}: Google warm-up error (non-fatal): {str(e)}")

    finally:
        try:
            await page.unroute("**/*", interceptor_handler)
        except Exception:
            pass
