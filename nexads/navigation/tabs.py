"""
nexads/navigation/tabs.py
Tab management: ensure correct tab is focused, process ad tabs, natural exit.
"""

import random
import asyncio
import time

from nexads.navigation.urls import extract_domain


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

                stay_time = random.randint(
                    config['ads']['min_time'],
                    config['ads']['max_time']
                )

                start_time = time.time()
                while time.time() - start_time < stay_time:
                    await perform_random_activity_fn(page, browser_context, worker_id, stay_time)
                    await asyncio.sleep(get_random_delay_fn(1, 3))

                await page.close()

            except Exception as e:
                print(f"Worker {worker_id}: Error processing ad tab: {str(e)}")
                continue

        return ad_tabs_processed

    except Exception as e:
        print(f"Worker {worker_id}: Error processing ad tabs: {str(e)}")
        return 0


async def natural_exit(browser_context, worker_id: int, get_random_delay_fn):
    """Perform natural exit by visiting Google then closing all tabs."""
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
                break

        if pages:
            try:
                page = pages[0]
                if not page.is_closed():
                    await page.goto("https://www.google.com", timeout=45000, wait_until="networkidle")
                    await asyncio.sleep(get_random_delay_fn(2, 5))
                    await page.close()
            except Exception as e:
                print(f"Worker {worker_id}: Error during Google visit in natural exit: {str(e)}")

        return True

    except Exception as e:
        print(f"Worker {worker_id}: Error during natural exit: {str(e)}")
        return False
