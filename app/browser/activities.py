"""
nexads/browser/activities.py
Human-like browser activities: scroll, hover, click.
"""

import asyncio
import random
import time

from app.browser.humanization import (
    clamp,
    choose_click_point,
    gaussian_ms,
    get_cursor_start,
    lognormal_seconds,
    move_mouse_humanly,
    set_cursor_position,
)


def _get_reading_phase(progress: float) -> str:
    """Simple state machine to keep activity sequencing coherent."""
    if progress < 0.15:
        return "arrival"
    if progress < 0.75:
        return "reading"
    if progress < 0.92:
        return "exploration"
    return "done"


async def _idle_mouse_jitter(
    page, interaction_state: dict | None, running: bool, duration_seconds: float
):
    """Create small mouse drifts during idle windows."""
    if duration_seconds <= 0:
        return

    end_time = time.time() + duration_seconds
    while running and time.time() < end_time:
        remaining = end_time - time.time()
        if remaining <= 0:
            break

        pause = min(lognormal_seconds(2.1, 0.5, 0.8, 4.2), remaining)
        if pause > 0:
            await asyncio.sleep(pause)

        if not running or time.time() >= end_time:
            break

        viewport = page.viewport_size or {"width": 1280, "height": 720}
        start_x, start_y = get_cursor_start(page, interaction_state)
        target_x = clamp(
            start_x + random.gauss(0, random.uniform(2, 8)), 1, viewport["width"] - 1
        )
        target_y = clamp(
            start_y + random.gauss(0, random.uniform(2, 8)), 1, viewport["height"] - 1
        )

        await move_mouse_humanly(page, (start_x, start_y), (target_x, target_y))
        set_cursor_position(interaction_state, target_x, target_y)


async def _get_activity_capabilities(page) -> dict:
    """Return currently feasible activity capabilities for the active page."""
    try:
        return await page.evaluate(
            """
            () => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (style.visibility === 'hidden' || style.display === 'none') return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 1 && rect.height > 1;
                };

                const doc = document.documentElement;
                const body = document.body;
                const scrollHeight = Math.max(
                    body ? body.scrollHeight : 0,
                    doc ? doc.scrollHeight : 0
                );
                const canScroll = scrollHeight > (window.innerHeight + 40);

                const hoverCandidates = document.querySelectorAll('a, button, img, [role="button"], p, h1, h2, h3, li, span');
                const clickCandidates = document.querySelectorAll('a, button, [onclick], [role="button"]');

                let canHover = false;
                for (const el of hoverCandidates) {
                    if (isVisible(el)) {
                        canHover = true;
                        break;
                    }
                }

                let canClick = false;
                for (const el of clickCandidates) {
                    if (isVisible(el)) {
                        canClick = true;
                        break;
                    }
                }

                return { can_scroll: canScroll, can_hover: canHover, can_click: canClick };
            }
            """
        )
    except Exception:
        # Be permissive on script failures so activity loop can still proceed.
        return {"can_scroll": True, "can_hover": True, "can_click": True}


async def random_scroll(
    page,
    browser,
    worker_id: int,
    ensure_correct_tab_fn,
    running: bool,
    phase: str = "reading",
    expected_url: str | None = None,
):
    """Perform human-like scrolling with occasional up-scroll and corrections."""
    try:
        target_url = expected_url or page.url
        page, success = await ensure_correct_tab_fn(
            browser, page, target_url, worker_id
        )
        if not success:
            print(f"Worker {worker_id}: Could not ensure correct tab for scrolling")
            return False

        print(f"Worker {worker_id}: Performing human-like scroll")

        height = await page.evaluate(
            "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
        )
        viewport_height = await page.evaluate("window.innerHeight")
        current_scroll = await page.evaluate("window.scrollY")

        if height <= viewport_height:
            print(f"Worker {worker_id}: Page is not scrollable")
            return False

        max_scroll = max(0, height - viewport_height)
        if max_scroll <= 0:
            return False

        up_chance = 0.28 if phase in {"reading", "exploration"} else 0.15
        if current_scroll < viewport_height * 0.5:
            up_chance *= 0.4

        direction = -1 if (current_scroll > 0 and random.random() < up_chance) else 1

        base_distance = viewport_height * random.uniform(0.35, 1.05)
        if phase == "arrival":
            base_distance *= random.uniform(0.55, 0.9)
        elif phase == "done":
            base_distance *= random.uniform(1.15, 1.7)

        candidate_distance = int(
            base_distance + random.gauss(0, viewport_height * 0.16)
        )
        candidate_distance = int(clamp(candidate_distance, 90, viewport_height * 2.0))

        available_distance = (
            int(max_scroll - current_scroll) if direction > 0 else int(current_scroll)
        )
        scroll_amount = min(candidate_distance, max(0, available_distance))
        if scroll_amount < 20:
            return False

        signed_scroll = scroll_amount if direction > 0 else -scroll_amount
        steps = int(clamp(scroll_amount / random.uniform(85, 175), 3, 12))
        step_size = signed_scroll / max(1, steps)

        for _ in range(steps):
            if not running:
                break

            jitter = max(12, abs(step_size) * 0.35)
            current_step = int(step_size + random.gauss(0, jitter))
            if current_step == 0:
                current_step = 15 if direction > 0 else -15

            await page.evaluate(
                "(distance) => window.scrollBy(0, distance)", current_step
            )
            await page.wait_for_timeout(gaussian_ms(190, 70, 80, 450))

            # Micro-corrections in opposite direction simulate wheel overshoot.
            if random.random() < 0.22:
                correction = int(-current_step * random.uniform(0.12, 0.28))
                await page.evaluate(
                    "(distance) => window.scrollBy(0, distance)", correction
                )
                await page.wait_for_timeout(gaussian_ms(120, 40, 55, 240))

        direction_text = "down" if direction > 0 else "up"
        print(
            f"Worker {worker_id}: Scrolled {direction_text} {scroll_amount}px in {steps} steps"
        )
        return True

    except Exception as e:
        print(f"Worker {worker_id}: Error during scrolling: {str(e)}")
        return False


async def random_hover(
    page,
    browser,
    worker_id: int,
    ensure_correct_tab_fn,
    running: bool,
    interaction_state: dict | None = None,
    expected_url: str | None = None,
):
    """Perform realistic mouse hover with tab checking."""
    try:
        target_url = expected_url or page.url
        page, success = await ensure_correct_tab_fn(
            browser, page, target_url, worker_id
        )
        if not success:
            print(f"Worker {worker_id}: Could not ensure correct tab for hovering")
            return

        print(f"Worker {worker_id}: Performing random hover")

        elements = await page.query_selector_all(
            'a, button, img, [role="button"], p, h1, h2, h3, li, span'
        )
        if not elements:
            print(f"Worker {worker_id}: No hoverable elements found")
            return

        visible_elements = []
        for element in elements:
            try:
                if await element.is_visible():
                    visible_elements.append(element)
            except Exception:
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

        try:
            tag_name = await element.evaluate("el => el.tagName")
        except Exception:
            tag_name = ""

        target_x, target_y = choose_click_point(box, tag_name)
        start_x, start_y = get_cursor_start(page, interaction_state)

        if running:
            await move_mouse_humanly(page, (start_x, start_y), (target_x, target_y))
            set_cursor_position(interaction_state, target_x, target_y)

        hover_time = lognormal_seconds(1.0, 0.45, 0.35, 3.4)
        await page.wait_for_timeout(int(hover_time * 1000))

        print(
            f"Worker {worker_id}: Hovered at {target_x:.0f},{target_y:.0f} for {hover_time:.1f}s"
        )

    except Exception as e:
        print(f"Worker {worker_id}: Error during hover: {str(e)}")


async def random_click(
    page,
    browser,
    worker_id: int,
    current_domain: str,
    is_ads_session: bool,
    ensure_correct_tab_fn,
    smart_click_fn,
    extract_domain_fn,
    interaction_state: dict | None = None,
    expected_url: str | None = None,
):
    """Find random same-domain clickable elements and click one."""
    try:
        target_url = expected_url or page.url
        page, success = await ensure_correct_tab_fn(
            browser, page, target_url, worker_id
        )
        if not success:
            print(f"Worker {worker_id}: Could not ensure correct tab for clicking")
            return False

        original_url = page.url

        elements = await page.query_selector_all("a, button, [onclick], [role=button]")
        if not elements:
            print(f"Worker {worker_id}: No clickable elements found")
            return False

        same_domain_elements = []
        for element in elements:
            try:
                href = await element.get_attribute("href") or ""
                if (
                    href
                    and not href.startswith("#")
                    and current_domain in extract_domain_fn(href)
                ):
                    same_domain_elements.append(element)
            except Exception:
                continue

        if not same_domain_elements:
            print(f"Worker {worker_id}: No same-domain elements found")
            return False

        element = random.choice(same_domain_elements)
        print(f"Worker {worker_id}: Attempting click on random element")

        if await smart_click_fn(
            page, worker_id, current_domain, element, is_ads_session, interaction_state
        ):
            await asyncio.sleep(lognormal_seconds(0.9, 0.45, 0.35, 2.8))
            return page.url != original_url

        return False

    except Exception as e:
        print(f"Worker {worker_id}: Random click error: {str(e)}")
        return False


async def perform_random_activity(
    page,
    browser,
    worker_id: int,
    stay_time: float,
    config: dict,
    running: bool,
    ensure_correct_tab_fn,
    smart_click_fn,
    extract_domain_fn,
    check_vignette_fn,
    is_ads_session: bool = False,
    interaction_state: dict | None = None,
    strict_target_url: str | None = None,
):
    """Perform randomized activities for the provided stay duration."""
    random_activity_enabled = config["browser"].get("random_activity", False)
    if not random_activity_enabled:
        return False

    activities_list = config["browser"].get("activities", [])
    if not activities_list:
        return False

    if interaction_state is None:
        interaction_state = {}

    try:
        expected_url = strict_target_url or page.url
        current_domain = extract_domain_fn(expected_url)
        blocked_by_url = interaction_state.setdefault("blocked_activities_by_url", {})

        activity_start = time.time()
        remaining_time = stay_time

        while remaining_time > 0 and running:
            page, success = await ensure_correct_tab_fn(
                browser, page, expected_url, worker_id
            )
            if not success:
                print(f"Worker {worker_id}: Lost correct tab during activities")
                return False

            current_domain = extract_domain_fn(page.url)
            await check_vignette_fn(page, worker_id)
            capabilities = await _get_activity_capabilities(page)

            raw_blocked = blocked_by_url.get(expected_url, [])
            blocked_activities = (
                set(raw_blocked) if isinstance(raw_blocked, list) else set()
            )
            if capabilities.get("can_scroll", True) and "scroll" in blocked_activities:
                blocked_activities.discard("scroll")

            blocked_by_url[expected_url] = sorted(blocked_activities)

            capability_log_key = (
                expected_url,
                bool(capabilities.get("can_scroll", True)),
                bool(capabilities.get("can_hover", True)),
                bool(capabilities.get("can_click", True)),
                tuple(sorted(blocked_activities)),
            )
            if interaction_state.get("last_capability_log_key") != capability_log_key:
                interaction_state["last_capability_log_key"] = capability_log_key
                print(
                    f"Worker {worker_id}: Activity capability "
                    f"scroll={capabilities.get('can_scroll', True)}, "
                    f"hover={capabilities.get('can_hover', True)}, "
                    f"click={capabilities.get('can_click', True)}, "
                    f"blocked={sorted(blocked_activities)}"
                )

            progress = (stay_time - remaining_time) / max(1.0, stay_time)
            phase = _get_reading_phase(progress)

            weighted_activities: list[tuple[str, float]] = []
            if (
                "scroll" in config["browser"]["activities"]
                and capabilities.get("can_scroll", True)
                and "scroll" not in blocked_activities
            ):
                weighted_activities.append(
                    (
                        "scroll",
                        {
                            "arrival": 0.65,
                            "reading": 0.60,
                            "exploration": 0.35,
                            "done": 0.55,
                        }[phase],
                    )
                )
            if (
                "click" in config["browser"]["activities"]
                and capabilities.get("can_click", True)
                and "click" not in blocked_activities
            ):
                weighted_activities.append(
                    (
                        "click",
                        {
                            "arrival": 0.10,
                            "reading": 0.10,
                            "exploration": 0.30,
                            "done": 0.25,
                        }[phase],
                    )
                )
            if (
                "hover" in config["browser"]["activities"]
                and capabilities.get("can_hover", True)
                and "hover" not in blocked_activities
            ):
                weighted_activities.append(
                    (
                        "hover",
                        {
                            "arrival": 0.25,
                            "reading": 0.30,
                            "exploration": 0.35,
                            "done": 0.20,
                        }[phase],
                    )
                )

            if not weighted_activities:
                backoff = min(lognormal_seconds(1.2, 0.45, 0.5, 2.4), remaining_time)
                if backoff > 0:
                    await _idle_mouse_jitter(page, interaction_state, running, backoff)
                elapsed = time.time() - activity_start
                remaining_time = stay_time - elapsed
                continue

            labels = [item[0] for item in weighted_activities]
            weights = [item[1] for item in weighted_activities]
            selected = random.choices(labels, weights=weights, k=1)[0]

            if selected == "scroll":
                scroll_ok = await random_scroll(
                    page,
                    browser,
                    worker_id,
                    ensure_correct_tab_fn,
                    running,
                    phase,
                    expected_url,
                )
                if not scroll_ok:
                    blocked_activities.add("scroll")
                    blocked_by_url[expected_url] = sorted(blocked_activities)
                    print(
                        f"Worker {worker_id}: Blocked activity 'scroll' for current URL state"
                    )
            elif selected == "click":
                await random_click(
                    page,
                    browser,
                    worker_id,
                    current_domain,
                    is_ads_session,
                    ensure_correct_tab_fn,
                    smart_click_fn,
                    extract_domain_fn,
                    interaction_state,
                    expected_url,
                )
            else:
                await random_hover(
                    page,
                    browser,
                    worker_id,
                    ensure_correct_tab_fn,
                    running,
                    interaction_state,
                    expected_url,
                )

            # Hard re-anchor after each activity in case a redirect happened mid-action.
            page, success = await ensure_correct_tab_fn(
                browser, page, expected_url, worker_id
            )
            if not success:
                print(
                    f"Worker {worker_id}: Could not recover target tab after activity"
                )
                return False

            elapsed = time.time() - activity_start
            remaining_time = stay_time - elapsed

            if remaining_time > 0:
                delay = min(lognormal_seconds(1.9, 0.5, 0.7, 4.8), remaining_time)
                if delay > 0:
                    await _idle_mouse_jitter(page, interaction_state, running, delay)
                    elapsed = time.time() - activity_start
                    remaining_time = stay_time - elapsed

            await check_vignette_fn(page, worker_id)

        return True

    except Exception as e:
        print(f"Worker {worker_id}: Error during random activities: {str(e)}")
        return False
