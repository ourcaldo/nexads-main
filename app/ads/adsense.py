"""
nexads/ads/adsense.py
AdSense ad detection, interaction, vignette handling, and smart click.
"""

from __future__ import annotations

import asyncio
import random

from app.browser.humanization import (
    choose_click_point,
    gaussian_ms,
    get_cursor_start,
    lognormal_seconds,
    move_mouse_humanly,
    set_cursor_position,
)


async def detect_adsense_ads(page):
    """Detect and return all visible AdSense ad elements on the current page."""
    try:
        ad_selectors = [
            'ins.adsbygoogle',
            'ins[class*="adsbygoogle"]',
            'div[id*="google_ads"]',
            'div[data-ad-client]',
            'div[data-ad-slot]',
            'iframe[src*="googleads"]',
            'iframe[src*="doubleclick.net"]',
            'iframe[src*="adservice.google.com"]',
            'div[class*="adsense"]'
        ]
        visible_ads = []

        for selector in ad_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    try:
                        if await element.is_visible():
                            box = await element.bounding_box()
                            if box and box['width'] > 0 and box['height'] > 0:
                                visible_ads.append(element)
                    except Exception:
                        continue
            except Exception:
                continue

        print(f"Found {len(visible_ads)} visible AdSense ads from {len(ad_selectors)} selectors")
        return visible_ads

    except Exception as e:
        print(f"Ad detection error: {str(e)}")
        return []


async def detect_vignette_ad(page) -> bool:
    """Detect if a vignette ad is showing by checking the URL fragment."""
    try:
        return "#google_vignette" in page.url
    except Exception as e:
        print(f"Vignette detection error: {str(e)}")
        return False


async def interact_with_vignette_ad(page, worker_id: int, extract_domain_fn) -> bool:
    """Attempt to interact with a vignette ad by clicking buttons/images inside it."""
    try:
        print(f"Worker {worker_id}: Attempting to interact with vignette ad")
        current_domain = extract_domain_fn(page.url)
        interaction_state: dict = {}

        radio_buttons = await page.query_selector_all('input[type="radio"]')
        if radio_buttons:
            print(f"Worker {worker_id}: Found {len(radio_buttons)} radio buttons in vignette")
            radio = random.choice(radio_buttons)
            if await smart_click(page, worker_id, current_domain, radio, interaction_state=interaction_state):
                print(f"Worker {worker_id}: Clicked radio button")

            submit_buttons = await page.query_selector_all(
                'button:has-text("Submit"), button:has-text("Done"), '
                'button:has-text("Continue"), button:has-text("Close")'
            )
            if submit_buttons:
                for button in submit_buttons:
                    try:
                        if await button.is_visible():
                            if await smart_click(
                                page, worker_id, current_domain, button,
                                interaction_state=interaction_state
                            ):
                                print(f"Worker {worker_id}: Clicked vignette submit button")
                                return True
                    except Exception:
                        continue

        buttons = await page.query_selector_all(
            'button, div[role="button"], a[role="button"]'
        )
        if buttons:
            print(f"Worker {worker_id}: Found {len(buttons)} buttons in vignette")
            for button in buttons:
                try:
                    if await button.is_visible():
                        if await smart_click(
                            page, worker_id, current_domain, button,
                            interaction_state=interaction_state
                        ):
                            print(f"Worker {worker_id}: Clicked vignette button")
                            return True
                except Exception:
                    continue

        images = await page.query_selector_all('img, svg')
        if images:
            print(f"Worker {worker_id}: Found {len(images)} images in vignette")
            for img in images:
                try:
                    if await img.is_visible():
                        if await smart_click(
                            page, worker_id, current_domain, img,
                            interaction_state=interaction_state
                        ):
                            print(f"Worker {worker_id}: Clicked vignette image")
                            return True
                except Exception:
                    continue

        vignette_container = await page.query_selector('div[class*="vignette"], div[id*="vignette"]')
        if vignette_container:
            try:
                if await smart_click(
                    page, worker_id, current_domain, vignette_container,
                    interaction_state=interaction_state
                ):
                    print(f"Worker {worker_id}: Clicked vignette container")
                    return True
            except Exception:
                pass

        print(f"Worker {worker_id}: Could not find any interactive elements in vignette")
        return False

    except Exception as e:
        print(f"Worker {worker_id}: Error interacting with vignette: {str(e)}")
        return False


async def check_and_handle_vignette(page, worker_id: int, extract_domain_fn) -> bool:
    """Check for a vignette ad and handle it if present."""
    try:
        if not await detect_vignette_ad(page):
            return False

        print(f"Worker {worker_id}: Vignette ad detected")
        success = await interact_with_vignette_ad(page, worker_id, extract_domain_fn)
        if success:
            print(f"Worker {worker_id}: Successfully interacted with vignette ad")
            await page.wait_for_timeout(gaussian_ms(1900, 280, 1200, 3200))
            return True

        return False

    except Exception as e:
        print(f"Worker {worker_id}: Error checking/handling vignette: {str(e)}")
        return False


async def interact_with_ads(page, browser, worker_id: int, extract_domain_fn) -> bool:
    """Click visible AdSense ads and prefer natural left-click behavior."""
    visible_ads = await detect_adsense_ads(page)
    if not visible_ads:
        print(f"Worker {worker_id}: No visible AdSense ads found on page")
        return False

    print(f"Worker {worker_id}: Found {len(visible_ads)} visible AdSense ads on page")

    context = page.context
    tabs_before = len(context.pages)
    clicked = False
    interaction_state: dict = {}

    random.shuffle(visible_ads)

    for ad in visible_ads:
        try:
            current_domain = extract_domain_fn(page.url)
            box = await ad.bounding_box()
            ad_position = f"({box['x']:.0f},{box['y']:.0f})" if box else "(unknown position)"
            print(f"Worker {worker_id}: Attempting to click ad at {ad_position}")

            if await smart_click(
                page,
                worker_id,
                current_domain,
                ad,
                is_ad_activity=True,
                interaction_state=interaction_state,
            ):
                await asyncio.sleep(lognormal_seconds(2.1, 0.35, 1.2, 4.2))
                tabs_after = len(context.pages)
                if tabs_after > tabs_before:
                    print(
                        f"Worker {worker_id}: Ad click successful - new tab opened "
                        f"(total tabs: {tabs_after})"
                    )
                    clicked = True
                    break

                print(
                    f"Worker {worker_id}: Ad click did not open new tab "
                    f"(total tabs remains: {tabs_after})"
                )
                await asyncio.sleep(lognormal_seconds(0.8, 0.4, 0.35, 2.0))

        except Exception as e:
            print(f"Worker {worker_id}: Error clicking visible ad: {str(e)}")
            await asyncio.sleep(lognormal_seconds(0.8, 0.4, 0.35, 2.0))
            continue

    return clicked


async def smart_click(page, worker_id: int, current_domain: str,
                      element=None, is_ad_activity: bool = False,
                      interaction_state: dict | None = None) -> bool:
    """Perform a smart click with curved movement and realistic click variance."""
    try:
        if not page or page.is_closed():
            print(f"Worker {worker_id}: Page is closed or invalid during smart click")
            return False

        if not element:
            elements = await page.query_selector_all("a, button, input[type='button'], input[type='submit']")
            if not elements:
                print(f"Worker {worker_id}: No clickable elements found")
                return False

            valid_elements = []
            for el in elements:
                try:
                    is_visible = await el.is_visible()
                    is_covered = await page.evaluate("""(element) => {
                        const rect = element.getBoundingClientRect();
                        const x = rect.left + rect.width / 2;
                        const y = rect.top + rect.height / 2;
                        const topElement = document.elementFromPoint(x, y);
                        return topElement !== element && !element.contains(topElement);
                    }""", el)
                    if is_visible and not is_covered:
                        valid_elements.append(el)
                except Exception:
                    continue

            if not valid_elements:
                print(f"Worker {worker_id}: No valid clickable elements found")
                return False

            element = random.choice(valid_elements)

        try:
            href = await element.get_attribute("href") or ""
        except Exception:
            href = "N/A"

        try:
            tag = await element.evaluate('el => el.tagName')
        except Exception:
            tag = "N/A"

        try:
            text_content = await element.text_content()
            text_preview = (text_content or "").strip()[:50]
        except Exception:
            text_preview = "N/A"

        element_info = f"Tag: {tag}, Text: {text_preview}"

        await element.scroll_into_view_if_needed(timeout=10000)
        box = await element.bounding_box()
        if not box:
            print(f"Worker {worker_id}: Could not get element position")
            return False

        click_x, click_y = choose_click_point(box, tag)
        start_x, start_y = get_cursor_start(page, interaction_state)

        await move_mouse_humanly(page, (start_x, start_y), (click_x, click_y))
        set_cursor_position(interaction_state, click_x, click_y)
        await page.wait_for_timeout(gaussian_ms(360, 100, 160, 820))

        click_delay = gaussian_ms(110, 35, 45, 240)

        try:
            if is_ad_activity:
                popup_opened = False
                try:
                    async with page.expect_popup(timeout=4500) as popup_info:
                        await page.mouse.click(
                            click_x, click_y, button="left", click_count=1, delay=click_delay
                        )
                    popup_page = await popup_info.value
                    popup_opened = bool(popup_page and not popup_page.is_closed())
                except Exception:
                    await page.mouse.click(
                        click_x, click_y, button="left", click_count=1, delay=click_delay
                    )

                print(
                    f"Worker {worker_id}: Left-clicked ad element via mouse "
                    f"(popup={popup_opened}): {href}\nElement: {element_info}"
                )
                return True

            await page.mouse.click(
                click_x, click_y, button="left", click_count=1, delay=click_delay
            )
            print(f"Worker {worker_id}: Clicked element via mouse: {href}\nElement: {element_info}")
            return True

        except Exception as e:
            print(
                f"Worker {worker_id}: Mouse click failed, trying native click: {str(e)}\n"
                f"Element: {element_info}"
            )

            try:
                if is_ad_activity:
                    popup_opened = False
                    try:
                        async with page.expect_popup(timeout=4500) as popup_info:
                            await element.click(timeout=10000, delay=click_delay)
                        popup_page = await popup_info.value
                        popup_opened = bool(popup_page and not popup_page.is_closed())
                    except Exception:
                        await element.click(timeout=10000, delay=click_delay)

                    print(
                        f"Worker {worker_id}: Left-clicked ad element via native click "
                        f"(popup={popup_opened}): {href}\nElement: {element_info}"
                    )
                    return True

                await element.click(timeout=10000, delay=click_delay)
                print(f"Worker {worker_id}: Clicked element via native click: {href}\nElement: {element_info}")
                return True

            except Exception as e2:
                print(
                    f"Worker {worker_id}: Native click failed, trying JS click: {str(e2)}\n"
                    f"Element: {element_info}"
                )
                try:
                    await page.evaluate("(element) => { element.click(); }", element)
                    print(f"Worker {worker_id}: Clicked element via JS: {href}\nElement: {element_info}")
                    return True
                except Exception as e3:
                    print(f"Worker {worker_id}: All click methods failed: {str(e3)}\nElement: {element_info}")
                    return False

    except Exception as e:
        print(f"Worker {worker_id}: Error performing smart click: {str(e)}")
        return False
