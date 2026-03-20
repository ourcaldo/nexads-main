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


async def check_page_health(page) -> dict:
    """Check if the current page loaded successfully or is in an error state.

    Returns {"healthy": bool, "reason": str}.
    """
    try:
        url = page.url or ""
        if url.startswith("chrome-error://") or url.startswith("about:neterror"):
            return {"healthy": False, "reason": "browser_error_page"}

        result = await page.evaluate("""() => {
            const title = (document.title || '').substring(0, 200);
            const bodyText = document.body
                ? document.body.innerText.substring(0, 800) : '';
            const combined = title + ' ' + bodyText;

            const errorPatterns = [
                'ERR_TIMED_OUT', 'ERR_CONNECTION_REFUSED', 'ERR_PROXY',
                'ERR_NAME_NOT_RESOLVED', 'ERR_NETWORK_CHANGED',
                'ERR_INTERNET_DISCONNECTED', 'ERR_CONNECTION_RESET',
                'ERR_SSL_PROTOCOL_ERROR', 'ERR_TUNNEL_CONNECTION_FAILED',
                '502 Bad Gateway', '503 Service', '504 Gateway Timeout',
                '403 Forbidden', '404 Not Found', '500 Internal Server',
                "This site can't be reached", "This page isn't working",
                'Unable to connect', 'Server not found',
                'Proxy Error', 'Connection timed out',
                'The connection was reset', 'Secure connection failed',
            ];

            for (const pattern of errorPatterns) {
                if (combined.includes(pattern))
                    return { healthy: false, reason: pattern };
            }

            if (!document.body || document.body.children.length === 0)
                return { healthy: false, reason: 'blank_page' };

            return { healthy: true, reason: 'ok' };
        }""")
        return result if isinstance(result, dict) else {"healthy": False, "reason": "invalid_result"}
    except Exception:
        return {"healthy": False, "reason": "evaluate_failed"}


async def _batch_scan_links(page, target_url: str, target_domain: str):
    """Scan all page links in a single JS call and return matching (element, type) pairs."""
    # Single JS call: get all resolved hrefs at once
    all_hrefs = await page.evaluate(
        "() => Array.from(document.querySelectorAll('a[href]'), a => a.href)"
    )

    # Filter in Python (instant, no async round-trips)
    matching_indices = []
    for i, href in enumerate(all_hrefs):
        if not href:
            continue
        if extract_domain(href) == target_domain:
            is_exact = target_url in href
            matching_indices.append((i, 'exact' if is_exact else 'domain'))

    # Sort: exact matches first
    matching_indices.sort(key=lambda x: 0 if x[1] == 'exact' else 1)

    if not matching_indices:
        return []

    # Single call to get element handles
    all_links = await page.query_selector_all('a[href]')
    return [
        (all_links[i], match_type)
        for i, match_type in matching_indices
        if i < len(all_links)
    ]


async def navigate_to_url_by_click(page, target_url: str, worker_id: int,
                                   ensure_correct_tab_fn, smart_click_fn,
                                   accept_cookies_fn, check_vignette_fn,
                                   random_navigation_fn, config: dict,
                                   interaction_state: dict | None = None):
    """Navigate to target URL by finding and clicking a matching link on the current page."""
    from app.core.automation import SessionFailedException

    target_domain = extract_domain(target_url)
    max_retries = 2
    retry_count = 0
    # Cap link attempts per retry to avoid spending hours on broken pages
    max_link_attempts_per_retry = 5

    # --- Try pre-scanned link from activity loop ---
    pre_scan = (interaction_state or {}).get("pre_scanned_nav")
    if pre_scan and pre_scan.get("target_url") == target_url:
        raw_href = pre_scan.get("raw_href", "")
        if raw_href:
            try:
                link = await page.evaluate_handle(
                    """(rawHref) => {
                        for (const a of document.querySelectorAll('a[href]')) {
                            if (a.getAttribute('href') === rawHref) return a;
                        }
                        return null;
                    }""", raw_href
                )
                element = link.as_element()
                if element:
                    attached = await page.evaluate("(el) => el && el.isConnected", element)
                    if attached:
                        print(f"Worker {worker_id}: Using pre-scanned link for navigation")
                        try:
                            await element.scroll_into_view_if_needed(timeout=5000)
                        except Exception:
                            pass
                        await page.wait_for_timeout(random.randint(300, 800))
                        current_domain = extract_domain(page.url)
                        if await smart_click_fn(page, worker_id, current_domain, element):
                            try:
                                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                            except Exception:
                                pass
                            if extract_domain(page.url) == target_domain:
                                print(f"Worker {worker_id}: Successfully navigated via pre-scanned link")
                                await asyncio.sleep(3)
                                if config['browser']['auto_accept_cookies']:
                                    await accept_cookies_fn(page)
                                await check_vignette_fn(page, worker_id)
                                return True
            except Exception:
                pass
        # Pre-scan didn't work, fall through to normal scanning
        if interaction_state:
            interaction_state.pop("pre_scanned_nav", None)

    while retry_count < max_retries:
        try:
            page, success = await ensure_correct_tab_fn(page.context, page, target_url, worker_id)
            if not success:
                print(f"Worker {worker_id}: Could not ensure correct tab for navigation")
                retry_count += 1
                continue

            health = await check_page_health(page)
            if not health.get("healthy", True):
                print(f"Worker {worker_id}: Page unhealthy, skipping link navigation: {health.get('reason')}")
                raise SessionFailedException(f"Page unhealthy: {health.get('reason')}")

            # Scroll to top so header/nav links are visible and interactable
            try:
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(random.randint(300, 700))
            except Exception:
                pass

            print(f"Worker {worker_id}: Scanning page for links to {target_domain}")

            matching_links = await _batch_scan_links(page, target_url, target_domain)

            link_attempts = 0
            for link, match_type in matching_links:
                if link_attempts >= max_link_attempts_per_retry:
                    print(f"Worker {worker_id}: Hit link attempt cap ({max_link_attempts_per_retry}), giving up on this retry")
                    break
                link_attempts += 1

                try:
                    scroll_success = False
                    scroll_attempts = 0

                    while scroll_attempts < 2 and not scroll_success:
                        try:
                            attached = await page.evaluate("(el) => el && el.isConnected", link)
                            if not attached:
                                raise Exception("Element is not attached to the DOM")
                            await link.scroll_into_view_if_needed(timeout=5000)
                            scroll_success = True
                        except Exception as e:
                            scroll_attempts += 1
                            if scroll_attempts == 2:
                                raise
                            await asyncio.sleep(0.5)

                    await page.wait_for_timeout(random.randint(500, 1500))

                    current_domain = extract_domain(page.url)
                    if await smart_click_fn(page, worker_id, current_domain, link):
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=15000)
                        except Exception:
                            pass  # Navigation may have completed anyway

                        # Check if we actually navigated to the target domain
                        post_click_domain = extract_domain(page.url)
                        if post_click_domain == target_domain:
                            print(f"Worker {worker_id}: Successfully clicked {match_type} match")
                            await asyncio.sleep(3)

                            if config['browser']['auto_accept_cookies']:
                                await accept_cookies_fn(page)

                            await check_vignette_fn(page, worker_id)
                            return True

                        print(f"Worker {worker_id}: Click did not navigate to target (at {post_click_domain})")

                except Exception as e:
                    print(f"Worker {worker_id}: Link click failed: {str(e)}")
                    continue

            print(f"Worker {worker_id}: No clickable links worked, trying random navigation")
            random_nav_success = await random_navigation_fn(page, worker_id, target_domain)
            if random_nav_success:
                return True

            # All links failed AND random navigation failed — count as a retry
            retry_count += 1
            print(f"Worker {worker_id}: Navigation retry {retry_count}/{max_retries}")
            if retry_count < max_retries:
                await asyncio.sleep(2)

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
            page, success = await ensure_correct_tab_fn(page.context, page, current_url, worker_id)
            if not success:
                print(f"Worker {worker_id}: Could not ensure correct tab for random navigation")
                retry_count += 1
                continue

            print(f"Worker {worker_id}: Attempting random navigation")
            original_url = page.url

            all_links = await page.query_selector_all('a[href]')
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

            for attempt in range(2):
                try:
                    await link.scroll_into_view_if_needed(timeout=5000)
                    break
                except Exception as e:
                    print(f"Worker {worker_id}: Scroll attempt {attempt + 1} failed: {str(e)}")
                    if attempt == 1:
                        raise
                    await asyncio.sleep(0.5)

            await page.wait_for_timeout(random.randint(500, 1500))

            current_domain = extract_domain(page.url)
            if await smart_click_fn(page, worker_id, current_domain, link):
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass

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
            else:
                print(f"Worker {worker_id}: Random click did not succeed")
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
