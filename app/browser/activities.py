"""
nexads/browser/activities.py
Human-like browser activities: scroll, hover, click.
"""

import random
import asyncio
import time


async def random_scroll(page, browser, worker_id: int, ensure_correct_tab_fn, running: bool):
    """Perform human-like scrolling with tab checking."""
    try:
        current_url = page.url
        page, success = await ensure_correct_tab_fn(browser, page, current_url, worker_id)
        if not success:
            print(f"Worker {worker_id}: Could not ensure correct tab for scrolling")
            return

        print(f"Worker {worker_id}: Performing human-like scroll")

        height = await page.evaluate("document.body.scrollHeight")
        viewport_height = await page.evaluate("window.innerHeight")

        if height <= viewport_height:
            print(f"Worker {worker_id}: Page is not scrollable")
            return

        scroll_amount = random.randint(int(height * 0.2), int(height * 0.8))
        steps = random.randint(3, 10)
        step_size = scroll_amount // steps

        for i in range(steps):
            if not running:
                break
            current_step = step_size + random.randint(-50, 50)
            await page.evaluate(f"window.scrollBy(0, {current_step})")
            await page.wait_for_timeout(random.randint(100, 500))

        print(f"Worker {worker_id}: Scrolled {scroll_amount}px in {steps} steps")

    except Exception as e:
        print(f"Worker {worker_id}: Error during scrolling: {str(e)}")


async def random_hover(page, browser, worker_id: int, ensure_correct_tab_fn, running: bool):
    """Perform realistic mouse hover with tab checking."""
    try:
        current_url = page.url
        page, success = await ensure_correct_tab_fn(browser, page, current_url, worker_id)
        if not success:
            print(f"Worker {worker_id}: Could not ensure correct tab for hovering")
            return

        print(f"Worker {worker_id}: Performing random hover")

        elements = await page.query_selector_all('a, button, img, div, span')
        if not elements:
            print(f"Worker {worker_id}: No hoverable elements found")
            return

        visible_elements = []
        for element in elements:
            try:
                if await element.is_visible():
                    visible_elements.append(element)
            except:
                continue

        if not visible_elements:
            print(f"Worker {worker_id}: No visible hoverable elements")
            return

        element = random.choice(visible_elements)
        await element.scroll_into_view_if_needed(timeout=10000)
        box = await element.bounding_box()
        if not box:
            print(f"Worker {worker_id}: Could not get element position")
            return

        steps = random.randint(5, 15)
        target_x = box['x'] + random.randint(0, int(box['width']))
        target_y = box['y'] + random.randint(0, int(box['height']))

        # Interpolate from current viewport center to target (not from 0,0)
        viewport = page.viewport_size or {'width': 1280, 'height': 720}
        start_x = viewport['width'] // 2
        start_y = viewport['height'] // 2

        for i in range(steps):
            if not running:
                break
            frac = (i + 1) / steps
            current_x = int(start_x + (target_x - start_x) * frac)
            current_y = int(start_y + (target_y - start_y) * frac)
            await page.mouse.move(current_x, current_y)
            await page.wait_for_timeout(random.randint(50, 200))

        await page.mouse.move(target_x, target_y)
        hover_time = random.uniform(0.5, 2.0)
        await page.wait_for_timeout(int(hover_time * 1000))

        print(f"Worker {worker_id}: Hovered at {target_x},{target_y} for {hover_time:.1f}s")

    except Exception as e:
        print(f"Worker {worker_id}: Error during hover: {str(e)}")


async def random_click(page, browser, worker_id: int, current_domain: str,
                       is_ads_session: bool, ensure_correct_tab_fn,
                       smart_click_fn, extract_domain_fn):
    """Find random same-domain clickable elements and click one."""
    try:
        current_url = page.url
        page, success = await ensure_correct_tab_fn(browser, page, current_url, worker_id)
        if not success:
            print(f"Worker {worker_id}: Could not ensure correct tab for clicking")
            return False

        original_url = page.url

        elements = await page.query_selector_all('a, button, [onclick], [role=button]')
        if not elements:
            print(f"Worker {worker_id}: No clickable elements found")
            return False

        same_domain_elements = []
        for element in elements:
            try:
                href = await element.get_attribute('href') or ''
                if href and not href.startswith('#') and current_domain in extract_domain_fn(href):
                    same_domain_elements.append(element)
            except:
                continue

        if not same_domain_elements:
            print(f"Worker {worker_id}: No same-domain elements found")
            return False

        element = random.choice(same_domain_elements)
        print(f"Worker {worker_id}: Attempting click on random element")

        if await smart_click_fn(page, worker_id, current_domain, element, is_ads_session):
            await asyncio.sleep(random.uniform(0.5, 1.5))
            return page.url != original_url

        return False

    except Exception as e:
        print(f"Worker {worker_id}: Random click error: {str(e)}")
        return False


async def perform_random_activity(page, browser, worker_id: int, stay_time: float,
                                  config: dict, running: bool,
                                  ensure_correct_tab_fn, smart_click_fn,
                                  extract_domain_fn, check_vignette_fn,
                                  is_ads_session: bool = False):
    """Perform random activities on the page for the given stay_time duration."""
    if not config['browser']['random_activity'] and not is_ads_session:
        return False

    try:
        current_url = page.url
        current_domain = extract_domain_fn(current_url)

        activity_start = time.time()
        remaining_time = stay_time

        while remaining_time > 0 and running:
            page, success = await ensure_correct_tab_fn(browser, page, current_url, worker_id)
            if not success:
                print(f"Worker {worker_id}: Lost correct tab during activities")
                return False

            # Refresh domain after every tab check — page may have navigated
            current_domain = extract_domain_fn(page.url)

            await check_vignette_fn(page, worker_id)

            activities = []
            if 'scroll' in config['browser']['activities']:
                activities.append(lambda: random_scroll(
                    page, browser, worker_id, ensure_correct_tab_fn, running))
            if 'click' in config['browser']['activities']:
                activities.append(lambda: random_click(
                    page, browser, worker_id, current_domain, is_ads_session,
                    ensure_correct_tab_fn, smart_click_fn, extract_domain_fn))
            if 'hover' in config['browser']['activities']:
                activities.append(lambda: random_hover(
                    page, browser, worker_id, ensure_correct_tab_fn, running))

            if activities:
                activity = random.choice(activities)
                await activity()

                elapsed = time.time() - activity_start
                remaining_time = stay_time - elapsed

                if remaining_time > 0:
                    delay = min(random.uniform(1, 3), remaining_time)
                    if delay > 0:
                        await asyncio.sleep(delay)
                        elapsed = time.time() - activity_start
                        remaining_time = stay_time - elapsed

            await check_vignette_fn(page, worker_id)

        return True

    except Exception as e:
        print(f"Worker {worker_id}: Error during random activities: {str(e)}")
        return False
