"""
nexads/navigation/tabs.py
Tab management: ensure correct tab is focused, process ad tabs, natural exit.
"""

import random
import asyncio
import time

from app.browser.humanization import clamp, lognormal_seconds
from app.navigation.urls import extract_domain


async def ensure_correct_tab(browser, page, target_url: str, worker_id: int,
                             config: dict, timeout: int = 60):
    """
    Ensure the correct tab is focused before performing activities.
    Returns (page, success) tuple.
    """
    if not config['browser'].get('prevent_redirects', True):
        return page, True

    start_time = time.time()
    attempts = 0
    target_domain = extract_domain(target_url)

    while time.time() - start_time < timeout:
        attempts += 1
        try:
            contexts = browser.contexts if hasattr(browser, 'contexts') else [browser]
            pages = []
            for context in contexts:
                try:
                    pages.extend(context.pages)
                except:
                    continue

            current_tab = page if page and not page.is_closed() else (pages[0] if pages else None)
            target_page = None

            for p in pages:
                try:
                    if not p.is_closed() and target_domain in p.url:
                        target_page = p
                        break
                except:
                    continue

            if not target_page:
                # Target tab not found — reuse or open new
                if len(pages) <= 1:
                    if current_tab:
                        try:
                            await current_tab.goto(target_url, timeout=90000, wait_until="networkidle")
                            await current_tab.bring_to_front()
                            print(f"Worker {worker_id}: Opened target URL in current tab")
                            return current_tab, True
                        except Exception as e:
                            print(f"Worker {worker_id}: Error loading target URL in current tab: {e}")
                            return None, False
                else:
                    context = contexts[0] if contexts else await browser.new_context()
                    try:
                        new_page = await context.new_page()
                        await new_page.goto(target_url, timeout=90000, wait_until="networkidle")
                        await new_page.bring_to_front()
                        print(f"Worker {worker_id}: Opened target URL in new tab")
                        return new_page, True
                    except Exception as e:
                        print(f"Worker {worker_id}: Failed to open new tab: {e}")
                        try:
                            if 'new_page' in locals() and not new_page.is_closed():
                                await new_page.close()
                        except:
                            pass

            else:
                if current_tab and target_page != current_tab:
                    await target_page.bring_to_front()
                    try:
                        await target_page.wait_for_load_state("networkidle", timeout=5000)
                    except:
                        pass
                    print(f"Worker {worker_id}: Focused on existing tab with {target_url}")
                return target_page, True

            await asyncio.sleep(1)

        except Exception as e:
            print(f"Worker {worker_id}: Unexpected error in ensure_correct_tab: {e}")
            await asyncio.sleep(1)

    print(f"Worker {worker_id}: Timeout ensuring correct tab for {target_url}")
    return None, False


async def process_ads_tabs(browser_context, worker_id: int, config: dict,
                           perform_random_activity_fn, get_random_delay_fn):
    """Process any ad tabs that were opened during the session."""
    try:
        try:
            pages = browser_context.pages
        except AttributeError:
            print(f"Worker {worker_id}: No pages found in browser context - natural exit")
            return 0

        if len(pages) <= 1:
            return 0

        print(f"Worker {worker_id}: Processing {len(pages)-1} ad tabs")
        config_urls = []

        for url_data in config['urls']:
            if url_data['random_page']:
                urls = [u.strip() for u in url_data['url'].split(',')]
                config_urls.extend(urls)
            else:
                config_urls.append(url_data['url'].strip())

        ad_tabs_processed = 0

        for page in pages:
            try:
                if page.is_closed():
                    continue

                current_url = page.url
                if any(extract_domain(url) in current_url for url in config_urls):
                    continue

                ad_tabs_processed += 1
                print(f"Worker {worker_id}: Processing ad tab: {current_url}")

                min_ads = int(config['ads']['min_time'])
                max_ads = int(config['ads']['max_time'])
                if min_ads >= max_ads:
                    base_stay = float(min_ads)
                else:
                    base_stay = lognormal_seconds((min_ads + max_ads) / 2, 0.55, min_ads, max_ads)

                try:
                    content_height = await page.evaluate(
                        "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
                    )
                except Exception:
                    content_height = 1600

                height_factor = clamp(content_height / 2600, 0.65, 2.1)
                stay_time = int(round(clamp(base_stay * height_factor, 5, 120)))

                # Realistic quick bounce behavior on some ad landings.
                if random.random() < 0.18:
                    stay_time = int(round(lognormal_seconds(8, 0.45, 5, 15)))

                interaction_state = {"cursor_position": None}
                print(
                    f"Worker {worker_id}: Ad tab dwell target {stay_time}s "
                    f"(content_height={int(content_height)})"
                )

                start_time = time.time()
                while time.time() - start_time < stay_time:
                    remaining = max(0.0, stay_time - (time.time() - start_time))
                    if remaining <= 0:
                        break

                    await perform_random_activity_fn(
                        page, browser_context, worker_id, remaining, True, interaction_state
                    )

                    idle_delay = min(lognormal_seconds(1.5, 0.45, 0.7, 3.8), remaining)
                    if idle_delay > 0:
                        await asyncio.sleep(idle_delay)

                await page.close()

            except Exception as e:
                print(f"Worker {worker_id}: Error processing ad tab: {str(e)}")
                continue

        return ad_tabs_processed

    except Exception as e:
        print(f"Worker {worker_id}: Error processing ad tabs: {str(e)}")
        return 0


async def natural_exit(browser_context, worker_id: int, get_random_delay_fn):
    """Perform varied, human-like session exit behavior."""
    try:
        try:
            pages = browser_context.pages
        except AttributeError:
            print(f"Worker {worker_id}: No pages found for natural exit")
            return False

        if not pages:
            return True

        print(f"Worker {worker_id}: Starting natural exit sequence")

        while len(pages) > 1:
            try:
                page = pages[-1]
                if not page.is_closed():
                    await page.close()
                pages = browser_context.pages
                await asyncio.sleep(get_random_delay_fn(1, 2))
            except Exception as e:
                print(f"Worker {worker_id}: Error closing tab during natural exit: {str(e)}")
                # Refresh page list and continue closing remaining tabs instead of breaking
                try:
                    pages = browser_context.pages
                except Exception:
                    break

        if pages:
            try:
                page = pages[0]
                if not page.is_closed():
                    exit_roll = random.random()
                    if exit_roll < 0.40:
                        strategy = "close_direct"
                    elif exit_roll < 0.60:
                        strategy = "google"
                    elif exit_roll < 0.75:
                        strategy = "random_site"
                    elif exit_roll < 0.90:
                        strategy = "new_tab"
                    else:
                        strategy = "linger"

                    print(f"Worker {worker_id}: Exit strategy = {strategy}")

                    if strategy == "google":
                        await page.goto("https://www.google.com", timeout=45000, wait_until="networkidle")
                        await asyncio.sleep(lognormal_seconds(2.5, 0.45, 1.2, 6.0))
                    elif strategy == "random_site":
                        site = random.choice([
                            "https://duckduckgo.com/",
                            "https://www.bing.com/",
                            "https://news.ycombinator.com/",
                            "https://www.wikipedia.org/",
                            "https://www.reddit.com/",
                        ])
                        await page.goto(site, timeout=45000, wait_until="networkidle")
                        await asyncio.sleep(lognormal_seconds(2.2, 0.45, 1.0, 5.5))
                    elif strategy == "new_tab":
                        await page.goto("about:blank", timeout=20000, wait_until="domcontentloaded")
                        await asyncio.sleep(lognormal_seconds(1.4, 0.4, 0.5, 3.0))
                    elif strategy == "linger":
                        if random.random() < 0.55:
                            await page.evaluate(
                                "(distance) => window.scrollBy(0, distance)",
                                int(random.gauss(220, 90)),
                            )
                        await asyncio.sleep(lognormal_seconds(2.8, 0.5, 1.2, 7.0))
                    else:
                        await asyncio.sleep(lognormal_seconds(1.2, 0.4, 0.5, 3.0))

                    await page.close()
            except Exception as e:
                print(f"Worker {worker_id}: Error during natural exit strategy: {str(e)}")

        return True

    except Exception as e:
        print(f"Worker {worker_id}: Error during natural exit: {str(e)}")
        return False
