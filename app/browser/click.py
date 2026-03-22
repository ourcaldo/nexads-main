"""
app/browser/click.py
Smart click primitive: curved mouse movement, realistic click variance, fallback chain.
"""

from __future__ import annotations

import random

from app.browser.humanization import (
    clamp,
    choose_click_point,
    get_cursor_start,
    move_mouse_humanly,
    set_cursor_position,
)
from app.core.timings import timing_ms


async def smart_click(page, worker_id: int, current_domain: str,
                      element=None, is_ad_activity: bool = False,
                      interaction_state: dict | None = None) -> bool:
    """Perform a smart click with curved movement and realistic click variance."""
    try:
        if not page:
            print(f"Worker {worker_id}: Page is closed or invalid during smart click")
            return False
        # Frame objects don't have is_closed(); only check on Page objects
        if hasattr(page, 'is_closed') and page.is_closed():
            print(f"Worker {worker_id}: Page is closed during smart click")
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

        is_mobile = (interaction_state or {}).get("is_mobile", False)
        start_x, start_y = get_cursor_start(page, interaction_state)
        viewport = page.viewport_size or {"width": 1280, "height": 720}

        if is_ad_activity:
            # --- Pre-hover: simulate noticing and reading the ad ---

            # 1. Move near the ad (50-150px from edge) — "noticing" it
            near_x = clamp(
                box["x"] + random.uniform(-150, box["width"] + 150),
                1, viewport["width"] - 1,
            )
            near_y = clamp(
                box["y"] + random.uniform(-80, -20),
                1, viewport["height"] - 1,
            )
            await move_mouse_humanly(page, (start_x, start_y), (near_x, near_y), is_mobile=is_mobile)
            set_cursor_position(interaction_state, near_x, near_y)
            await page.wait_for_timeout(timing_ms("ad_notice"))

            # 2. Move into the ad — first hover point (reading the ad)
            hover1_x = clamp(
                box["x"] + random.uniform(box["width"] * 0.15, box["width"] * 0.85),
                box["x"] + 1, box["x"] + box["width"] - 1,
            )
            hover1_y = clamp(
                box["y"] + random.uniform(box["height"] * 0.2, box["height"] * 0.8),
                box["y"] + 1, box["y"] + box["height"] - 1,
            )
            await move_mouse_humanly(page, (near_x, near_y), (hover1_x, hover1_y), is_mobile=is_mobile)
            set_cursor_position(interaction_state, hover1_x, hover1_y)
            await page.wait_for_timeout(timing_ms("ad_read_hover"))

            # 3. Optional second hover point within the ad (40% chance — scanning)
            if random.random() < 0.40:
                hover2_x = clamp(
                    box["x"] + random.uniform(box["width"] * 0.1, box["width"] * 0.9),
                    box["x"] + 1, box["x"] + box["width"] - 1,
                )
                hover2_y = clamp(
                    box["y"] + random.uniform(box["height"] * 0.1, box["height"] * 0.9),
                    box["y"] + 1, box["y"] + box["height"] - 1,
                )
                await move_mouse_humanly(
                    page, (hover1_x, hover1_y), (hover2_x, hover2_y), is_mobile=is_mobile
                )
                set_cursor_position(interaction_state, hover2_x, hover2_y)
                await page.wait_for_timeout(timing_ms("ad_scan_hover"))

            # 4. Move to final click point
            click_x, click_y = choose_click_point(box, tag)
            prev_x, prev_y = get_cursor_start(page, interaction_state)
            await move_mouse_humanly(page, (prev_x, prev_y), (click_x, click_y), is_mobile=is_mobile)
            set_cursor_position(interaction_state, click_x, click_y)
            await page.wait_for_timeout(timing_ms("click_dwell"))

        else:
            # --- Normal click: direct move to click point ---
            click_x, click_y = choose_click_point(box, tag)
            await move_mouse_humanly(page, (start_x, start_y), (click_x, click_y), is_mobile=is_mobile)
            set_cursor_position(interaction_state, click_x, click_y)
            await page.wait_for_timeout(timing_ms("click_dwell"))

        click_delay = timing_ms("click_delay")

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
                    f"Worker {worker_id}: All click methods failed: {str(e2)}\n"
                    f"Element: {element_info}"
                )
                return False

    except Exception as e:
        print(f"Worker {worker_id}: Error performing smart click: {str(e)}")
        return False
