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
from app.browser.humanization import lognormal_seconds
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
    get_social_referrer,
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
from app.core.automation import SessionFailedException


# After this many consecutive session failures, force-kill all child browser
# processes and take a longer cooldown before retrying.
MAX_CONSECUTIVE_FAILURES = 5
FAILURE_COOLDOWN_SECONDS = 120


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
        min_val = min_t if min_t is not None else self.ctx.config["delay"]["min_time"]
        max_val = max_t if max_t is not None else self.ctx.config["delay"]["max_time"]
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

    # --- Main session loop ---

    async def run(self):
        """Main worker loop: runs sessions until stopped or session limit reached."""
        wid = self.worker_id
        ctx = self.ctx

        try:
            if not ctx.config["urls"]:
                print(f"Worker {wid}: No URLs configured")
                return

            while ctx.running:
                session_start_time = time.time()
                self._redirect_budget_states.clear()

                if (
                    ctx.config["session"]["enabled"]
                    and ctx.config["session"]["count"] > 0
                    and self.session_count >= ctx.config["session"]["count"]
                ):
                    print(f"Worker {wid}: Session count limit reached")
                    break

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
                        await asyncio.sleep(10)
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
                        await asyncio.sleep(10)
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

                    # --- URL PROCESSING ---
                    for url_index, url_data in enumerate(ctx.config["urls"]):
                        if not ctx.running:
                            break

                        if _session_expired():
                            print(f"Worker {wid}: Max session time reached ({session_max_seconds}s)")
                            break

                        if url_data["random_page"]:
                            urls = [
                                u.strip() for u in url_data["url"].split(",") if u.strip()
                            ]
                            url = random.choice(urls) if urls else url_data["url"].strip()
                        else:
                            url = url_data["url"].strip()

                        next_url = None
                        if url_index + 1 < len(ctx.config["urls"]):
                            next_data = ctx.config["urls"][url_index + 1]
                            if not next_data["random_page"]:
                                next_url = next_data["url"].strip()

                        interaction_state.pop("pre_scanned_nav", None)
                        interaction_state.pop("ad_attempted_this_page", None)

                        print(
                            f"Worker {wid}: [URL {url_index + 1}/{len(ctx.config['urls'])}] Visiting: {url}"
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
                            referrer_types = ctx.config["referrer"]["types"]
                            referrer_type = random.choice(referrer_types)

                            if referrer_type == "social":
                                is_mobile = interaction_state.get("is_mobile", False)
                                social = get_social_referrer(url, is_mobile)
                                if social["referer"]:
                                    await page.set_extra_http_headers({"referer": social["referer"]})
                                    print(
                                        f"Worker {wid}: Using {social['platform']} referrer: {social['referer']}"
                                    )
                                nav_url = social["url"]
                                print(f"Worker {wid}: Loading initial URL directly")
                                try:
                                    await page.goto(
                                        nav_url, timeout=30000, wait_until="domcontentloaded"
                                    )
                                    await asyncio.sleep(3)
                                    # Clear the referer header so subsequent requests don't carry it
                                    await page.set_extra_http_headers({})
                                except Exception as e:
                                    print(
                                        f"Worker {wid}: Error visiting URL: {str(e)}"
                                    )
                                    _emit_step(
                                        "url_navigation",
                                        "failed",
                                        url_value=url,
                                        url_idx=url_index + 1,
                                        reason_code="initial_direct_goto_failed",
                                        error=e,
                                        duration_ms=int(
                                            (time.time() - url_step_started) * 1000
                                        ),
                                    )
                                    raise SessionFailedException(
                                        "Failed to visit initial URL"
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
                                    await asyncio.sleep(3)
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
                                    await asyncio.sleep(3)
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

                        print(f"Worker {wid}: Waiting 3s for page to settle...")
                        await asyncio.sleep(3)

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
                                    lognormal_seconds(1.1, 0.4, 0.4, 2.8), remaining_time
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

                    await asyncio.sleep(1)

                if session_successful:
                    self.successful_sessions += 1
                    self.consecutive_failures = 0
                    delay = self.get_delay(10, 30)
                    print(f"Worker {wid}: Session successful, waiting {delay}s")
                    _emit_step("session", "ok", reason_code="session_completed")
                else:
                    self.consecutive_failures += 1
                    if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        print(
                            f"Worker {wid}: {self.consecutive_failures} consecutive failures, "
                            f"killing orphan browsers and cooling down {FAILURE_COOLDOWN_SECONDS}s"
                        )
                        self._kill_children(wid)
                        _emit_step(
                            "session", "failed",
                            reason_code="consecutive_failure_cooldown",
                            meta={"consecutive_failures": self.consecutive_failures},
                        )
                        self.consecutive_failures = 0
                        await asyncio.sleep(FAILURE_COOLDOWN_SECONDS)
                        continue
                    delay = self.get_delay(30, 60)
                    print(f"Worker {wid}: Session failed, waiting {delay}s")

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
