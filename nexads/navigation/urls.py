"""
nexads/navigation/urls.py
URL navigation: domain extraction, click-based navigation, random navigation.
"""

import random
import asyncio
from urllib.parse import urlparse


def extract_domain(url: str) -> str:
    """Extract the netloc domain from a URL."""
    parsed = urlparse(url)
    return parsed.netloc


async def navigate_to_url_by_click(page, target_url: str, worker_id: int,
                                   ensure_correct_tab_fn, smart_click_fn,
                                   accept_cookies_fn, check_vignette_fn,
                                   random_navigation_fn, config: dict):
    """Navigate to target URL by finding and clicking a matching link on the current page."""
    from nexads.core.worker import SessionFailedException

    target_domain = extract_domain(target_url)
    max_retries = 2
    retry_count = 0

    while retry_count < max_retries:
        try:
            page, success = await ensure_correct_tab_fn(page.context.browser, page, target_url, worker_id)
            if not success:
                print(f"Worker {worker_id}: Could not ensure correct tab for navigation")
                retry_count += 1
                continue

            print(f"Worker {worker_id}: Scanning page for links to {target_domain}")

            all_links = await page.query_selector_all('a[href]:visible')
            if not all_links:
                print(f"Worker {worker_id}: No visible links found on page")
                retry_count += 1
                continue

            matching_links = []
            for link in all_links:
                try:
                    href = await link.get_attribute('href')
                    if href and target_url in href:
                        matching_links.append((link, 'exact'))
                    elif href and target_domain in href:
                        matching_links.append((link, 'domain'))
                except:
                    continue

            matching_links.sort(key=lambda x: 0 if x[1] == 'exact' else 1)

            for link, match_type in matching_links:
                try:
                    scroll_success = False
                    scroll_attempts = 0

                    while scroll_attempts < 3 and not scroll_success:
                        try:
                            attached = await page.evaluate("(el) => el && el.isConnected", link)
                            if not attached:
                                raise Exception("Element is not attached to the DOM")
                            await link.scroll_into_view_if_needed(timeout=22500)
                            scroll_success = True
                        except Exception as e:
                            scroll_attempts += 1
                            if scroll_attempts == 3:
                                raise
                            await asyncio.sleep(1)

                    await page.wait_for_timeout(random.randint(500, 1500))

                    current_domain = extract_domain(page.url)
                    if await smart_click_fn(page, worker_id, current_domain, link):
                        await page.wait_for_load_state("networkidle", timeout=45000)
                        print(f"Worker {worker_id}: Successfully clicked {match_type} match")

                        if config['browser']['auto_accept_cookies']:
                            await accept_cookies_fn(page)

                        await check_vignette_fn(page, worker_id)
                        return True

                except Exception as e:
                    print(f"Worker {worker_id}: Link click failed: {str(e)}")
                    continue

            print(f"Worker {worker_id}: No matching links found, trying random navigation")
            random_nav_success = await random_navigation_fn(page, worker_id, target_domain)
            if random_nav_success:
                return True

        except Exception as e:
            print(f"Worker {worker_id}: Error during URL click navigation: {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                await asyncio.sleep(2)
            continue

    print(f"Worker {worker_id}: Failed to navigate to {target_url} after {max_retries} attempts")
    raise SessionFailedException(f"Failed to navigate to {target_url}")


async def random_navigation(page, worker_id: int, target_domain: str,
                            ensure_correct_tab_fn, smart_click_fn,
                            accept_cookies_fn, check_vignette_fn, config: dict):
    """Perform random navigation by clicking a random domain-matched link."""
    max_retries = 2
    retry_count = 0

    while retry_count < max_retries:
        try:
            current_url = page.url
            page, success = await ensure_correct_tab_fn(page.context.browser, page, current_url, worker_id)
            if not success:
                print(f"Worker {worker_id}: Could not ensure correct tab for random navigation")
                retry_count += 1
                continue

            print(f"Worker {worker_id}: Attempting random navigation")
            original_url = page.url

            all_links = await page.query_selector_all('a[href]:visible')
            if not all_links:
                print(f"Worker {worker_id}: No visible links found for random navigation")
                retry_count += 1
                continue

            if target_domain:
                domain_links = []
                for link in all_links:
                    try:
                        href = await link.get_attribute('href')
                        if href and target_domain in href:
                            domain_links.append(link)
                    except:
                        continue

                if domain_links:
                    print(f"Worker {worker_id}: Found {len(domain_links)} links matching target domain")
                    all_links = domain_links
                else:
                    print(f"Worker {worker_id}: No links matching target domain found")

            link = random.choice(all_links)

            for attempt in range(3):
                try:
                    await link.scroll_into_view_if_needed(timeout=22500)
                    break
                except Exception as e:
                    print(f"Worker {worker_id}: Scroll attempt {attempt + 1} failed: {str(e)}")
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1)

            await page.wait_for_timeout(random.randint(500, 1500))

            current_domain = extract_domain(page.url)
            if await smart_click_fn(page, worker_id, current_domain, link):
                await page.wait_for_load_state("networkidle", timeout=45000)

                if config['browser']['auto_accept_cookies']:
                    await accept_cookies_fn(page)

                await check_vignette_fn(page, worker_id)

                if page.url != original_url:
                    print(f"Worker {worker_id}: Random navigation successful to {page.url}")
                    return True
                else:
                    print(f"Worker {worker_id}: Random navigation did not change URL")
                    retry_count += 1
                    continue

        except Exception as e:
            print(f"Worker {worker_id}: Error during random navigation: {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                await asyncio.sleep(2)
            continue

    print(f"Worker {worker_id}: Max retries reached for random navigation")
    return False
