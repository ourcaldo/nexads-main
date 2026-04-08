"""
app/core/session.py
SessionRunner: encapsulates the per-worker session loop and its bound helpers.
Extracted from worker.py to reduce file size and improve readability.
"""

import random
import asyncio
import time

from app.browser.setup import configure_browser, cleanup_browser
from app.browser.activities import perform_random_activity
from app.browser.humanization import (
    lognormal_seconds,
    get_cursor_start,
    move_mouse_humanly,
    set_cursor_position,
)
from app.core.timings import timing_ms, timing_seconds
from app.navigation.urls import (
    extract_domain,
    check_page_health,
    navigate_to_url_by_click,
    random_navigation,
)
from app.navigation.referrer import (
    get_random_keyword,
    perform_organic_search,
    accept_google_cookies,
    navigate_social_referrer,
    get_social_referrer,
    warm_google_profile,
)
from app.navigation.consent import handle_consent_dialog, try_dismiss_consent
from app.navigation.tabs import (
    NavigationIntent,
    ensure_correct_tab,
    process_ads_tabs,
    natural_exit,
)
from app.core.telemetry import emit_worker_event, emit_mobile_fingerprint_event, emit_heartbeat
from app.ads.adsense import check_and_handle_vignette
from app.browser.click import smart_click
from app.ads.dispatcher import dispatch_ad_interaction
from app.navigation.explorer import discover_internal_links, select_next_link, normalize_path
from app.core.automation import SessionFailedException


# After this many consecutive session failures, force-kill all child browser
# processes and take a longer cooldown before retrying.
MAX_CONSECUTIVE_FAILURES = 5


class SessionRunner:
    """Runs the session loop for a single worker, encapsulating all bound helpers."""

    def __init__(self, ctx, worker_id: int, kill_children_fn):
        self.ctx = ctx
        self.worker_id = worker_id
        self._kill_children = kill_children_fn

        self.session_count = 0
        self.successful_sessions = 0
        self.ads_session_count = 0
        self.successful_ads_sessions = 0
        self.redirect_recoveries = 0
        self.consecutive_failures = 0

        self._redirect_budget_states: dict[str, dict] = {}

    # --- Bound helpers (formerly closures over ctx) ---

    def get_delay(self, min_t=None, max_t=None):
        """Compute a human-like delay using lognormal distribution."""
        min_val = min_t if min_t is not None else 3
        max_val = max_t if max_t is not None else 10
        if min_val >= max_val:
            return int(min_val)
        median = (min_val + max_val) / 2
        return int(round(lognormal_seconds(median, 0.45, min_val, max_val)))

    def _build_intent(self, url: str, intent_type: str, timeout: int) -> NavigationIntent:
        allowed_suffixes = self.ctx.config.get("browser", {}).get(
            "allowed_redirect_suffixes", []
        )
        if not isinstance(allowed_suffixes, list):
            allowed_suffixes = []

        max_seconds = int(
            self.ctx.config.get("browser", {}).get("redirect_guard_max_seconds", timeout)
        )
        return NavigationIntent(
            expected_domain=extract_domain(url),
            allowed_domain_suffixes=[
                str(v) for v in allowed_suffixes if str(v).strip()
            ],
            intent_type=intent_type,
            max_recovery_seconds=max(1, max_seconds),
        )

    def _build_budget_limits(self, intent_type: str) -> dict:
        browser_cfg = self.ctx.config.get("browser", {})
        if intent_type == "ad_landing_intent":
            return {
                "max_recoveries": int(
                    browser_cfg.get("redirect_budget_recoveries_ad", 6)
                ),
                "max_new_tabs": int(browser_cfg.get("redirect_budget_new_tabs_ad", 3)),
            }
        if intent_type == "recovery_intent":
            return {
                "max_recoveries": int(
                    browser_cfg.get("redirect_budget_recoveries_recovery", 10)
                ),
                "max_new_tabs": int(
                    browser_cfg.get("redirect_budget_new_tabs_recovery", 3)
                ),
            }
        return {
            "max_recoveries": int(
                browser_cfg.get("redirect_budget_recoveries_target", 8)
            ),
            "max_new_tabs": int(browser_cfg.get("redirect_budget_new_tabs_target", 2)),
        }

    async def ensure_tab(
        self, browser, page, url, wid, timeout=60, intent_type="target_page_intent"
    ):
        """Ensure correct tab with intent-based redirect budget tracking."""
        budget_key = f"{intent_type}:{url}"
        budget_state = self._redirect_budget_states.setdefault(
            budget_key,
            {"recoveries": 0, "new_tab_openings": 0, "last_reason_code": ""},
        )
        before_recoveries = int(budget_state.get("recoveries", 0))

        result_page, success = await ensure_correct_tab(
            browser,
            page,
            url,
            wid,
            self.ctx.config,
            timeout,
            intent=self._build_intent(url, intent_type, timeout),
            budget_state=budget_state,
            budget_limits=self._build_budget_limits(intent_type),
        )

        after_recoveries = int(budget_state.get("recoveries", 0))
        self.redirect_recoveries += max(0, after_recoveries - before_recoveries)

        if not success:
            reason = budget_state.get("last_reason_code", "unknown")
            print(
                f"Worker {wid}: Redirect guard failed "
                f"(intent={intent_type}, reason={reason}, url={url})"
            )

        return result_page, success

    async def _ensure_tab_target(self, browser, page, url, wid, timeout=60):
        return await self.ensure_tab(browser, page, url, wid, timeout, "target_page_intent")

    async def _ensure_tab_ad(self, browser, page, url, wid, timeout=60):
        return await self.ensure_tab(browser, page, url, wid, timeout, "ad_landing_intent")

    async def _check_vignette(self, page, wid):
        await try_dismiss_consent(page, wid)
        return await check_and_handle_vignette(page, wid, extract_domain)

    async def _smart_click(
        self, page, wid, domain, element=None, is_ad=False, interaction_state=None
    ):
        return await smart_click(page, wid, domain, element, is_ad, interaction_state)

    async def _perform_activity(
        self, page, browser, wid, stay_time, is_ads=False, interaction_state=None,
        target_url=None, next_url=None,
    ):
        ensure_tab_fn = self._ensure_tab_ad if is_ads else self._ensure_tab_target

        ads_fn = None
        if is_ads and interaction_state is not None:
            async def _dispatch_ads(p, b, w, edf, max_duration=0):
                return await dispatch_ad_interaction(
                    p, b, w, edf, self.ctx.config, interaction_state, max_duration
                )
            ads_fn = _dispatch_ads

        return await perform_random_activity(
            page,
            browser,
            wid,
            stay_time,
            self.ctx.config,
            self.ctx.running,
            ensure_tab_fn,
            self._smart_click,
            extract_domain,
            self._check_vignette,
            is_ads,
            interaction_state,
            target_url if not is_ads else None,
            interact_with_ads_fn=ads_fn,
            next_url=next_url,
        )

    # --- Explorer mode ---

    async def _run_explorer_session(
        self, page, browser, wid, ctx, interaction_state,
        is_ads_session, gate_url, explorer_cfg,
        _session_expired, _session_remaining, _emit_step,
    ):
        """Autonomous same-domain browsing from a gate URL."""
        gate_domain = extract_domain(gate_url)
        visited_paths: set[str] = {normalize_path(gate_url)}
        page_count = 0
        min_stay = int(explorer_cfg.get("min_time", 30))
        max_stay = int(explorer_cfg.get("max_time", 60))
        back_count = 0
        max_back = 3

        while ctx.running and not _session_expired():
            page_count += 1
            current_url = page.url
            print(f"Worker {wid}: [Explorer page {page_count}] {current_url}")

            # --- Consent + vignette ---
            await try_dismiss_consent(page, wid)
            await self._check_vignette(page, wid)

            # --- Stay time ---
            if min_stay >= max_stay:
                stay_time = min_stay
            else:
                stay_time = int(round(
                    lognormal_seconds((min_stay + max_stay) / 2, 0.5, min_stay, max_stay)
                ))
            remaining_budget = _session_remaining()
            if remaining_budget < float("inf") and stay_time > remaining_budget:
                stay_time = max(1, int(remaining_budget))

            _settle = timing_seconds("page_settle")
            await asyncio.sleep(_settle)

            # Reset per-page ad state
            interaction_state.pop("ad_attempted_this_page", None)
            interaction_state.pop("ad_min_engagement_ratio", None)

            # Disable random_click during explorer — explorer handles its own navigation
            interaction_state["explorer_mode"] = True

            print(f"Worker {wid}: Explorer staying {stay_time}s on page {page_count}")
            _emit_step(
                "explorer_page", "started",
                url_value=current_url,
                url_idx=page_count,
                duration_ms=stay_time * 1000,
            )

            await self._perform_activity(
                page, browser, wid, stay_time,
                is_ads_session, interaction_state,
                target_url=current_url,
            )

            interaction_state.pop("explorer_mode", None)

            _emit_step(
                "explorer_page", "ok",
                url_value=current_url,
                url_idx=page_count,
            )

            if _session_expired() or not ctx.running:
                break

            # --- Discover and navigate to next page ---
            candidates = await discover_internal_links(page, gate_domain, visited_paths)
            selected = select_next_link(candidates)

            if not selected:
                # Dead end — go back
                back_count += 1
                if back_count > max_back:
                    print(f"Worker {wid}: Explorer exhausted back attempts, ending session")
                    break
                print(f"Worker {wid}: Explorer dead end, going back ({back_count}/{max_back})")
                try:
                    await page.go_back(timeout=15000, wait_until="domcontentloaded")
                    await asyncio.sleep(timing_seconds("page_settle"))
                except Exception as e:
                    print(f"Worker {wid}: Explorer go_back failed: {e}")
                    break
                # Re-discover after going back
                candidates = await discover_internal_links(page, gate_domain, visited_paths)
                selected = select_next_link(candidates)
                if not selected:
                    print(f"Worker {wid}: Explorer no links after go_back, ending session")
                    break
            else:
                back_count = 0

            # --- Click the selected link ---
            target_href = selected["href"]
            target_path = normalize_path(target_href)
            print(f"Worker {wid}: Explorer navigating to: {target_href}")

            try:
                # Find the element on page by matching href
                link_elements = await page.query_selector_all('a[href]')
                click_target = None
                for el in link_elements:
                    try:
                        el_href = await el.get_attribute("href")
                        if not el_href:
                            continue
                        # Match by full resolved URL or raw href
                        el_resolved = await el.evaluate("el => el.href")
                        if el_resolved == target_href:
                            if await el.is_visible():
                                click_target = el
                                break
                    except Exception:
                        continue

                if not click_target:
                    print(f"Worker {wid}: Explorer could not find link element, skipping")
                    visited_paths.add(target_path)
                    continue

                clicked = await self._smart_click(
                    page, wid, gate_domain, click_target, False, interaction_state
                )

                if clicked:
                    # Wait for navigation
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=30000)
                    except Exception:
                        pass
                    await asyncio.sleep(timing_seconds("page_settle"))
                    visited_paths.add(target_path)
                    # Also add the actual URL we landed on (may differ due to redirects)
                    visited_paths.add(normalize_path(page.url))
                else:
                    print(f"Worker {wid}: Explorer click failed, marking as visited")
                    visited_paths.add(target_path)

            except Exception as e:
                print(f"Worker {wid}: Explorer navigation error: {e}")
                visited_paths.add(target_path)

        print(f"Worker {wid}: Explorer session done — visited {page_count} pages")

    # --- Main session loop ---

    async def run(self):
        """Main worker loop: runs sessions until stopped or session limit reached."""
        wid = self.worker_id
        ctx = self.ctx

        try:
            _explorer_on = (ctx.config.get("explorer", {}).get("enabled", False)
                            and ctx.config.get("explorer", {}).get("gate_url", "").strip())
            if not _explorer_on and not ctx.config["urls"]:
                print(f"Worker {wid}: No URLs configured")
                return

            while ctx.running:
                session_start_time = time.time()
                self._redirect_budget_states.clear()

                if (
                    ctx.config["session"]["enabled"]
                    and ctx.config["session"]["count"] > 0
                ):
                    # Reserve one slot atomically from the global session budget.
                    with ctx.global_session_lock:
                        if ctx.global_session_count.value >= ctx.config["session"]["count"]:
                            print(f"Worker {wid}: Global session count limit reached")
                            break
                        ctx.global_session_count.value += 1

                ads_ctr = ctx.config.get("ads", {}).get("ctr", 0)
                is_ads_session = random.random() * 100 < ads_ctr

                if is_ads_session:
                    print(f"Worker {wid}: Starting AD INTERACTION session")
                    self.ads_session_count += 1
                else:
                    print(f"Worker {wid}: Starting normal session")

                self.session_count += 1
                session_id = f"w{wid}-s{self.session_count}-{int(time.time() * 1000)}"
                session_successful = False
                browser = None
                context = None
                is_persistent_context = False
                interaction_state = {"cursor_position": None}
                fingerprint_mode = "desktop"
                fallback_reason = ""

                session_max_seconds = ctx.config["session"]["max_time"] * 60 if ctx.config["session"]["max_time"] > 0 else 0
                session_deadline = (session_start_time + session_max_seconds) if session_max_seconds > 0 else 0

                def _session_remaining() -> float:
                    if session_deadline <= 0:
                        return float("inf")
                    return max(0.0, session_deadline - time.time())

                def _session_expired() -> bool:
                    return session_deadline > 0 and time.time() >= session_deadline

                def _emit_step(
                    step_name: str,
                    status: str,
                    url_value: str = "",
                    url_idx: int | None = None,
                    intent_type: str = "",
                    reason_code: str = "",
                    error: Exception | None = None,
                    duration_ms: int | None = None,
                    meta: dict | None = None,
                ):
                    emit_worker_event(
                        worker_id=wid,
                        session_id=session_id,
                        url_index=url_idx,
                        step_name=step_name,
                        status=status,
                        url=url_value,
                        intent_type=intent_type,
                        reason_code=reason_code,
                        error_type=type(error).__name__ if error else "",
                        error_message=str(error) if error else "",
                        duration_ms=duration_ms,
                        meta=meta,
                    )

                _emit_step(
                    "session",
                    "started",
                    reason_code="session_started",
                    meta={"is_ads_session": is_ads_session},
                )

                try:
                    # --- BROWSER INIT ---
                    browser_init_started = time.time()
                    browser_setup = await configure_browser(
                        ctx.config, wid, self.get_delay
                    )
                    if not browser_setup:
                        print(f"Worker {wid}: Failed to initialize browser")
                        _emit_step(
                            "browser_init",
                            "failed",
                            reason_code="configure_browser_returned_none",
                            duration_ms=int((time.time() - browser_init_started) * 1000),
                        )
                        await asyncio.sleep(timing_seconds("browser_retry"))
                        continue

                    is_persistent_context = browser_setup.get("is_persistent_context", False)
                    browser = browser_setup.get("browser")

                    if not is_persistent_context and not browser:
                        print(
                            f"Worker {wid}: Browser setup returned without browser instance"
                        )
                        _emit_step(
                            "browser_init",
                            "failed",
                            reason_code="browser_setup_missing_browser",
                            duration_ms=int((time.time() - browser_init_started) * 1000),
                        )
                        await asyncio.sleep(timing_seconds("browser_retry"))
                        continue

                    _emit_step(
                        "browser_init",
                        "ok",
                        duration_ms=int((time.time() - browser_init_started) * 1000),
                    )

                    fingerprint_mode = str(browser_setup.get("fingerprint_mode", "desktop"))
                    interaction_state["is_mobile"] = (fingerprint_mode == "mobile")
                    fallback_reason = str(browser_setup.get("fallback_reason", "") or "")
                    emit_mobile_fingerprint_event(
                        worker_id=wid,
                        event_type="session_fingerprint_mode",
                        session_id=session_id,
                        strategy_mode="active"
                        if fingerprint_mode == "mobile"
                        else "disabled",
                        final_mode=fingerprint_mode,
                        reason=fallback_reason,
                        success=True,
                    )

                    if is_persistent_context:
                        context = browser_setup.get("context")
                        browser = context
                        pages = context.pages
                        page = pages[0] if pages else await context.new_page()
                        print(
                            f"Worker {wid}: Using CloakBrowser persistent context"
                        )
                    else:
                        context_kwargs = dict(browser_setup.get("context_options") or {})
                        context = await browser.new_context(**context_kwargs)
                        page = await context.new_page()

                    def _random_nav(p, w, td):
                        return random_navigation(
                            p, w, td,
                            self.ensure_tab,
                            self._smart_click,
                            accept_google_cookies,
                            self._check_vignette,
                            ctx.config,
                        )

                    # --- GOOGLE PROFILE WARM-UP (not counted in session time) ---
                    await warm_google_profile(page, wid, ctx.config, max_seconds=60)

                    # --- VISIT SOCIAL PLATFORM FOR COOKIES (if social referrer) ---
                    referrer_types = ctx.config["referrer"]["types"]
                    _pre_referrer_type = random.choice(referrer_types)
                    _pre_social_info = None

                    if _pre_referrer_type == "social":
                        is_mobile = interaction_state.get("is_mobile", False)
                        _pre_social_info = get_social_referrer("", is_mobile)
                        platform = _pre_social_info["platform"]
                        _PLATFORM_HOMEPAGES = {
                            "Facebook": "https://www.facebook.com/",
                            "Instagram": "https://www.instagram.com/",
                            "Linkedin": "https://www.linkedin.com/",
                            "Snapchat": "https://www.snapchat.com/",
                            "Threads": "https://www.threads.net/",
                            "Tiktok": "https://www.tiktok.com/",
                            "Twitter": "https://x.com/",
                        }
                        homepage = _PLATFORM_HOMEPAGES.get(platform)
                        if homepage:
                            print(f"Worker {wid}: Visiting {platform} for cookies")
                            try:
                                await page.goto(
                                    homepage, timeout=20000,
                                    wait_until="domcontentloaded",
                                )
                                await page.wait_for_timeout(
                                    timing_ms("social_settle")
                                )

                                # Move cursor to a random starting spot
                                sx, sy = get_cursor_start(page, interaction_state)
                                viewport = page.viewport_size or {"width": 1280, "height": 720}
                                tx = random.uniform(viewport["width"] * 0.15, viewport["width"] * 0.85)
                                ty = random.uniform(viewport["height"] * 0.2, viewport["height"] * 0.7)
                                is_mobile = interaction_state.get("is_mobile", False)
                                await move_mouse_humanly(page, (sx, sy), (tx, ty), is_mobile=is_mobile)
                                set_cursor_position(interaction_state, tx, ty)

                                # 1-3 scroll events with varied distances
                                num_scrolls = random.randint(1, 3)
                                for _ in range(num_scrolls):
                                    await page.mouse.wheel(0, random.randint(100, 450))
                                    await page.wait_for_timeout(
                                        timing_ms("social_scroll_gap")
                                    )

                                # 35% chance: hover on a visible element
                                if random.random() < 0.35:
                                    try:
                                        elements = await page.query_selector_all(
                                            'a, img, span, p, h1, h2, h3'
                                        )
                                        visible = []
                                        for el in elements[:30]:
                                            try:
                                                if await el.is_visible():
                                                    visible.append(el)
                                                    if len(visible) >= 8:
                                                        break
                                            except Exception:
                                                continue
                                        if visible:
                                            target_el = random.choice(visible)
                                            box = await target_el.bounding_box()
                                            if box:
                                                hx = box["x"] + box["width"] * random.uniform(0.2, 0.8)
                                                hy = box["y"] + box["height"] * random.uniform(0.2, 0.8)
                                                cx, cy = get_cursor_start(page, interaction_state)
                                                await move_mouse_humanly(page, (cx, cy), (hx, hy), is_mobile=is_mobile)
                                                set_cursor_position(interaction_state, hx, hy)
                                                await page.wait_for_timeout(timing_ms("hover_dwell"))
                                    except Exception:
                                        pass

                                # Brief idle with mouse jitter
                                await page.wait_for_timeout(
                                    timing_ms("social_settle")
                                )
                                print(f"Worker {wid}: {platform} cookies acquired")
                            except Exception as e:
                                print(
                                    f"Worker {wid}: {platform} visit error (non-fatal): {str(e)}"
                                )

                    # --- URL PROCESSING ---
                    explorer_cfg = ctx.config.get("explorer", {})
                    explorer_enabled = explorer_cfg.get("enabled", False) and explorer_cfg.get("gate_url", "").strip()

                    if explorer_enabled:
                        _explorer_urls = [{"url": explorer_cfg["gate_url"].strip(),
                                           "min_time": int(explorer_cfg.get("min_time", 30)),
                                           "max_time": int(explorer_cfg.get("max_time", 60))}]
                    else:
                        _explorer_urls = ctx.config["urls"]

                    for url_index, url_data in enumerate(_explorer_urls):
                        if not ctx.running:
                            break

                        if _session_expired():
                            print(f"Worker {wid}: Max session time reached ({session_max_seconds}s)")
                            break

                        url = url_data["url"].strip()

                        next_url = None
                        if url_index + 1 < len(_explorer_urls):
                            next_data = _explorer_urls[url_index + 1]
                            next_url = next_data["url"].strip()

                        interaction_state.pop("pre_scanned_nav", None)
                        interaction_state.pop("ad_attempted_this_page", None)
                        interaction_state.pop("ad_min_engagement_ratio", None)

                        print(
                            f"Worker {wid}: [URL {url_index + 1}/{len(_explorer_urls)}] Visiting: {url}"
                        )
                        url_step_started = time.time()
                        _emit_step(
                            "url_navigation",
                            "started",
                            url_value=url,
                            url_idx=url_index + 1,
                        )

                        # --- FIRST URL ---
                        if url_index == 0:
                            referrer_type = _pre_referrer_type

                            if referrer_type == "social":
                                is_mobile = interaction_state.get("is_mobile", False)
                                _forced_platform = (
                                    _pre_social_info["platform"]
                                    if _pre_social_info else ""
                                )
                                try:
                                    success = await navigate_social_referrer(
                                        page, url, wid, is_mobile,
                                        platform=_forced_platform,
                                    )
                                    if not success:
                                        raise SessionFailedException(
                                            "Social referrer navigation failed"
                                        )
                                    await asyncio.sleep(timing_seconds("page_settle"))
                                except SessionFailedException:
                                    raise
                                except Exception as e:
                                    print(
                                        f"Worker {wid}: Error with social referrer: {str(e)}"
                                    )
                                    _emit_step(
                                        "url_navigation",
                                        "failed",
                                        url_value=url,
                                        url_idx=url_index + 1,
                                        reason_code="social_referrer_failed",
                                        error=e,
                                        duration_ms=int(
                                            (time.time() - url_step_started) * 1000
                                        ),
                                    )
                                    raise SessionFailedException(
                                        "Failed to visit initial URL via social referrer"
                                    )

                            elif referrer_type == "organic":
                                keyword = get_random_keyword(ctx.config)
                                if not keyword:
                                    print(f"Worker {wid}: No valid keyword available")
                                    raise SessionFailedException(
                                        "No valid keyword available"
                                    )
                                print(f"Worker {wid}: Using keyword: {keyword}")
                                target_domain = extract_domain(url)
                                if not await perform_organic_search(
                                    page,
                                    keyword,
                                    target_domain,
                                    wid,
                                    ctx.config,
                                    extract_domain,
                                ):
                                    print(f"Worker {wid}: Organic search failed")
                                    _emit_step(
                                        "url_navigation",
                                        "failed",
                                        url_value=url,
                                        url_idx=url_index + 1,
                                        reason_code="organic_search_failed",
                                        duration_ms=int(
                                            (time.time() - url_step_started) * 1000
                                        ),
                                    )
                                    raise SessionFailedException("Organic search failed")

                            else:
                                print(f"Worker {wid}: Loading initial URL directly")
                                try:
                                    await page.goto(
                                        url, timeout=30000, wait_until="domcontentloaded"
                                    )
                                    await asyncio.sleep(timing_seconds("page_settle"))
                                except Exception as e:
                                    print(
                                        f"Worker {wid}: Error visiting URL: {str(e)}"
                                    )
                                    _emit_step(
                                        "url_navigation",
                                        "failed",
                                        url_value=url,
                                        url_idx=url_index + 1,
                                        reason_code="initial_other_goto_failed",
                                        error=e,
                                        duration_ms=int(
                                            (time.time() - url_step_started) * 1000
                                        ),
                                    )
                                    raise SessionFailedException(
                                        "Failed to visit initial URL"
                                    )

                        # --- SUBSEQUENT URLS ---
                        else:
                            print(f"Worker {wid}: Navigating to next URL in sequence")
                            try:
                                await navigate_to_url_by_click(
                                    page,
                                    url,
                                    wid,
                                    self.ensure_tab,
                                    self._smart_click,
                                    accept_google_cookies,
                                    self._check_vignette,
                                    _random_nav,
                                    ctx.config,
                                    interaction_state=interaction_state,
                                )
                            except SessionFailedException:
                                print(
                                    f"Worker {wid}: Falling back to direct navigation"
                                )
                                try:
                                    await page.goto(
                                        url, timeout=30000, wait_until="domcontentloaded"
                                    )
                                    await asyncio.sleep(timing_seconds("page_settle"))
                                except Exception as e:
                                    print(
                                        f"Worker {wid}: Error visiting URL: {str(e)}"
                                    )
                                    _emit_step(
                                        "url_navigation",
                                        "failed",
                                        url_value=url,
                                        url_idx=url_index + 1,
                                        reason_code="sequence_fallback_goto_failed",
                                        error=e,
                                        duration_ms=int(
                                            (time.time() - url_step_started) * 1000
                                        ),
                                    )
                                    raise SessionFailedException(
                                        "Failed to navigate to URL"
                                    )

                        page, success = await self._ensure_tab_target(
                            browser, page, url, wid, timeout=25
                        )
                        if not success or not page:
                            _emit_step(
                                "ensure_tab",
                                "failed",
                                url_value=url,
                                url_idx=url_index + 1,
                                intent_type="target_page_intent",
                                reason_code="target_recovery_after_navigation_failed",
                            )
                            raise SessionFailedException(
                                "Could not recover target tab after navigation"
                            )

                        _emit_step(
                            "ensure_tab",
                            "ok",
                            url_value=url,
                            url_idx=url_index + 1,
                            intent_type="target_page_intent",
                            duration_ms=int((time.time() - url_step_started) * 1000),
                        )

                        health = await check_page_health(page)
                        if not health.get("healthy", True):
                            reason = health.get("reason", "unknown")
                            print(f"Worker {wid}: Page unhealthy after navigation: {reason}")
                            _emit_step(
                                "page_health",
                                "failed",
                                url_value=url,
                                url_idx=url_index + 1,
                                reason_code=f"unhealthy_{reason}",
                            )
                            continue

                        if ctx.config["browser"]["auto_accept_cookies"]:
                            await accept_google_cookies(page)

                        page, success = await self._ensure_tab_target(
                            browser, page, url, wid, timeout=20
                        )
                        if not success or not page:
                            _emit_step(
                                "ensure_tab",
                                "failed",
                                url_value=url,
                                url_idx=url_index + 1,
                                intent_type="target_page_intent",
                                reason_code="target_recovery_after_cookies_failed",
                            )
                            raise SessionFailedException(
                                "Could not recover target tab after cookie handling"
                            )

                        gdpr_max_wait = int(
                            ctx.config.get("browser", {}).get("gdpr_max_wait_seconds", 12)
                        )
                        gdpr_on_fail = (
                            str(
                                ctx.config.get("browser", {}).get(
                                    "gdpr_on_fail", "continue"
                                )
                            )
                            .strip()
                            .lower()
                        )

                        consent_result = await handle_consent_dialog(
                            page, wid, max_wait_seconds=gdpr_max_wait
                        )
                        consent_status = consent_result.get("status")
                        if consent_status == "unresolved":
                            print(
                                f"Worker {wid}: Consent unresolved "
                                f"(reason={consent_result.get('reason')}, attempts={consent_result.get('attempts')})"
                            )
                            _emit_step(
                                "consent",
                                "failed",
                                url_value=url,
                                url_idx=url_index + 1,
                                reason_code=f"consent_unresolved_{gdpr_on_fail}",
                                meta=consent_result,
                            )
                            if gdpr_on_fail == "skip_url":
                                print(
                                    f"Worker {wid}: Skipping URL due to unresolved consent"
                                )
                                continue
                            if gdpr_on_fail == "abort_session":
                                raise SessionFailedException("Consent unresolved")
                        else:
                            _emit_step(
                                "consent",
                                "ok",
                                url_value=url,
                                url_idx=url_index + 1,
                                reason_code=str(consent_result.get("reason", "")),
                                meta=consent_result,
                            )

                        page, success = await self._ensure_tab_target(
                            browser, page, url, wid, timeout=20
                        )
                        if not success or not page:
                            _emit_step(
                                "ensure_tab",
                                "failed",
                                url_value=url,
                                url_idx=url_index + 1,
                                intent_type="target_page_intent",
                                reason_code="target_recovery_after_consent_failed",
                            )
                            raise SessionFailedException(
                                "Could not recover target tab after consent handling"
                            )

                        await self._check_vignette(page, wid)

                        page, success = await self._ensure_tab_target(
                            browser, page, url, wid, timeout=20
                        )
                        if not success or not page:
                            _emit_step(
                                "ensure_tab",
                                "failed",
                                url_value=url,
                                url_idx=url_index + 1,
                                intent_type="target_page_intent",
                                reason_code="target_recovery_after_vignette_failed",
                            )
                            raise SessionFailedException(
                                "Could not recover target tab after vignette handling"
                            )

                        if _session_expired():
                            print(f"Worker {wid}: Session deadline reached before activity loop")
                            break

                        min_stay = int(url_data["min_time"])
                        max_stay = int(url_data["max_time"])
                        if min_stay >= max_stay:
                            stay_time = min_stay
                        else:
                            stay_time = int(
                                round(
                                    lognormal_seconds(
                                        (min_stay + max_stay) / 2, 0.5, min_stay, max_stay
                                    )
                                )
                            )

                        remaining_budget = _session_remaining()
                        if remaining_budget < float("inf") and stay_time > remaining_budget:
                            stay_time = max(1, int(remaining_budget))

                        _settle_delay = timing_seconds("page_settle")
                        print(f"Worker {wid}: Waiting {_settle_delay:.1f}s for page to settle...")
                        await asyncio.sleep(_settle_delay)

                        print(
                            f"Worker {wid}: Staying on page for {stay_time} seconds"
                        )
                        _emit_step(
                            "activity_loop",
                            "started",
                            url_value=url,
                            url_idx=url_index + 1,
                            duration_ms=stay_time * 1000,
                        )

                        activity_start = time.time()
                        remaining_time = stay_time
                        while remaining_time > 0 and ctx.running and not _session_expired():
                            elapsed = time.time() - activity_start
                            remaining_time = stay_time - elapsed

                            await self._perform_activity(
                                page,
                                browser,
                                wid,
                                remaining_time,
                                is_ads_session,
                                interaction_state,
                                target_url=url,
                                next_url=next_url,
                            )

                            elapsed = time.time() - activity_start
                            remaining_time = stay_time - elapsed

                            if remaining_time > 0:
                                delay = min(
                                    timing_seconds("session_activity"), remaining_time
                                )
                                if delay > 0:
                                    await asyncio.sleep(delay)

                        _emit_step(
                            "activity_loop",
                            "ok",
                            url_value=url,
                            url_idx=url_index + 1,
                            duration_ms=int((time.time() - activity_start) * 1000),
                        )

                        _emit_step(
                            "url_navigation",
                            "ok",
                            url_value=url,
                            url_idx=url_index + 1,
                            duration_ms=int((time.time() - url_step_started) * 1000),
                        )

                    # --- EXPLORER MODE: continue autonomous browsing ---
                    if explorer_enabled and not _session_expired() and ctx.running:
                        _emit_step("explorer_session", "started",
                                   url_value=explorer_cfg["gate_url"].strip())
                        await self._run_explorer_session(
                            page, browser, wid, ctx, interaction_state,
                            is_ads_session,
                            explorer_cfg["gate_url"].strip(),
                            explorer_cfg,
                            _session_expired, _session_remaining, _emit_step,
                        )
                        _emit_step("explorer_session", "ok",
                                   url_value=explorer_cfg["gate_url"].strip())

                    if is_ads_session:
                        if interaction_state.get("ad_click_success"):
                            self.successful_ads_sessions += 1
                            _emit_step("ad_click", "ok", reason_code="ad_clicked_during_activity")
                        else:
                            _emit_step("ad_click", "failed", reason_code="no_ad_click_during_session")

                    session_successful = True

                    session_min_seconds = ctx.config.get("session", {}).get("min_time", 0) * 60
                    if session_min_seconds > 0:
                        elapsed = time.time() - session_start_time
                        remaining_min = session_min_seconds - elapsed
                        if remaining_min > 1:
                            print(f"Worker {wid}: Session completed early, padding {int(remaining_min)}s to meet min_time")
                            await asyncio.sleep(remaining_min)

                except SessionFailedException as e:
                    print(f"Worker {wid}: Session marked as failed: {str(e)}")
                    _emit_step(
                        "session", "failed", reason_code="session_failed_exception", error=e
                    )
                    session_successful = False
                except Exception as e:
                    print(f"Worker {wid}: Critical error: {str(e)}")
                    _emit_step(
                        "session",
                        "failed",
                        reason_code="session_critical_exception",
                        error=e,
                    )
                    session_successful = False

                finally:
                    try:
                        if context:
                            await process_ads_tabs(
                                context, wid, ctx.config, self._perform_activity, self.get_delay
                            )
                            await natural_exit(context, wid, self.get_delay)
                        if is_persistent_context and context:
                            await cleanup_browser(None, wid, context=context)
                        elif browser:
                            await cleanup_browser(browser, wid)
                    except Exception as e:
                        print(f"Worker {wid}: Error during cleanup: {str(e)}")

                    await asyncio.sleep(timing_seconds("session_retry"))

                if session_successful:
                    self.successful_sessions += 1
                    self.consecutive_failures = 0
                    delay = timing_seconds("session_success")
                    print(f"Worker {wid}: Session successful, waiting {delay:.0f}s")
                    _emit_step("session", "ok", reason_code="session_completed")
                else:
                    self.consecutive_failures += 1
                    if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        cooldown = timing_seconds("failure_cooldown")
                        print(
                            f"Worker {wid}: {self.consecutive_failures} consecutive failures, "
                            f"killing orphan browsers and cooling down {cooldown:.0f}s"
                        )
                        self._kill_children(wid)
                        _emit_step(
                            "session", "failed",
                            reason_code="consecutive_failure_cooldown",
                            meta={"consecutive_failures": self.consecutive_failures},
                        )
                        self.consecutive_failures = 0
                        await asyncio.sleep(cooldown)
                        continue
                    delay = timing_seconds("session_failure")
                    print(f"Worker {wid}: Session failed, waiting {delay:.0f}s")

                emit_mobile_fingerprint_event(
                    worker_id=wid,
                    event_type="session_outcome",
                    session_id=session_id,
                    strategy_mode="active"
                    if fingerprint_mode == "mobile"
                    else (
                        "dry_run"
                        if fingerprint_mode == "dry_run"
                        else "disabled"
                    ),
                    final_mode=fingerprint_mode,
                    success=session_successful,
                    reason=fallback_reason,
                )

                emit_heartbeat(wid, self.session_count, self.successful_sessions)

                await asyncio.sleep(delay)

        except Exception as e:
            print(f"Worker {wid}: FATAL ERROR: {str(e)}")
            self._kill_children(wid)
        finally:
            ctx.session_counts[wid] = self.session_count
            ctx.successful_sessions[wid] = self.successful_sessions
            ctx.ads_session_counts[wid] = self.ads_session_count
            ctx.successful_ads_sessions[wid] = self.successful_ads_sessions

            print(
                f"Worker {wid}: Session completed - "
                f"Total: {self.session_count}, "
                f"Success: {self.successful_sessions}, "
                f"Ads: {self.ads_session_count} ({self.successful_ads_sessions} successful), "
                f"RedirectRecoveries: {self.redirect_recoveries}"
            )
