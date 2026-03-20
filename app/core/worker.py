"""
nexads/core/worker.py
Worker session logic: WorkerContext, worker_session, run_worker, run_worker_async.
"""

import random
import asyncio
import time
import os
import subprocess
from dataclasses import dataclass

# After this many consecutive session failures, force-kill all child browser
# processes and take a longer cooldown before retrying.
MAX_CONSECUTIVE_FAILURES = 5
FAILURE_COOLDOWN_SECONDS = 120

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
from app.ads.adsense import check_and_handle_vignette, smart_click
from app.ads.dispatcher import dispatch_ad_interaction


@dataclass
class WorkerContext:
    """Shared state passed to every worker function."""

    config: dict
    running: bool
    pending_ads_sessions: object  # multiprocessing.Value proxy
    session_counts: object  # multiprocessing.Manager dict proxy
    successful_sessions: object  # multiprocessing.Manager dict proxy
    ads_session_counts: object  # multiprocessing.Manager dict proxy
    successful_ads_sessions: object  # multiprocessing.Manager dict proxy


from app.core.automation import SessionFailedException


def _kill_child_browser_processes(worker_id: int):
    """Kill orphaned browser processes (camoufox/chromium) that are children of this worker."""
    my_pid = os.getpid()
    killed = 0
    try:
        # Find all child PIDs of this worker process
        result = subprocess.run(
            ["pgrep", "-P", str(my_pid)],
            capture_output=True, text=True, timeout=5,
        )
        child_pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
        for pid_str in child_pids:
            try:
                os.kill(int(pid_str), 9)
                killed += 1
            except (ProcessLookupError, ValueError):
                pass
    except Exception:
        # Fallback: use pkill to kill browser processes by name for this process tree
        for name in ("camoufox", "firefox", "chromium", "chrome"):
            try:
                subprocess.run(
                    ["pkill", "-9", "-P", str(my_pid), "-f", name],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass
    if killed:
        print(f"Worker {worker_id}: Force-killed {killed} orphaned browser process(es)")


async def worker_session(ctx: WorkerContext, worker_id: int):
    """Main worker loop: runs sessions until stopped or session limit reached."""
    session_count = 0
    successful_sessions = 0
    ads_session_count = 0
    successful_ads_sessions = 0
    redirect_recoveries = 0
    consecutive_failures = 0

    # Build bound helpers that close over ctx
    def get_delay(min_t=None, max_t=None):
        min_val = min_t if min_t is not None else ctx.config["delay"]["min_time"]
        max_val = max_t if max_t is not None else ctx.config["delay"]["max_time"]
        if min_val >= max_val:
            return int(min_val)
        median = (min_val + max_val) / 2
        return int(round(lognormal_seconds(median, 0.45, min_val, max_val)))

    redirect_budget_states: dict[str, dict] = {}

    def _build_intent(url: str, intent_type: str, timeout: int) -> NavigationIntent:
        allowed_suffixes = ctx.config.get("browser", {}).get(
            "allowed_redirect_suffixes", []
        )
        if not isinstance(allowed_suffixes, list):
            allowed_suffixes = []

        max_seconds = int(
            ctx.config.get("browser", {}).get("redirect_guard_max_seconds", timeout)
        )
        return NavigationIntent(
            expected_domain=extract_domain(url),
            allowed_domain_suffixes=[
                str(v) for v in allowed_suffixes if str(v).strip()
            ],
            intent_type=intent_type,
            max_recovery_seconds=max(1, max_seconds),
        )

    def _build_budget_limits(intent_type: str) -> dict:
        browser_cfg = ctx.config.get("browser", {})
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

    async def _ensure_tab(
        browser, page, url, wid, timeout=60, intent_type="target_page_intent"
    ):
        nonlocal redirect_recoveries
        budget_key = f"{intent_type}:{url}"
        budget_state = redirect_budget_states.setdefault(
            budget_key,
            {"recoveries": 0, "new_tab_openings": 0, "last_reason_code": ""},
        )
        before_recoveries = int(budget_state.get("recoveries", 0))

        result_page, success = await ensure_correct_tab(
            browser,
            page,
            url,
            wid,
            ctx.config,
            timeout,
            intent=_build_intent(url, intent_type, timeout),
            budget_state=budget_state,
            budget_limits=_build_budget_limits(intent_type),
        )

        after_recoveries = int(budget_state.get("recoveries", 0))
        redirect_recoveries += max(0, after_recoveries - before_recoveries)

        if not success:
            reason = budget_state.get("last_reason_code", "unknown")
            print(
                f"Worker {wid}: Redirect guard failed "
                f"(intent={intent_type}, reason={reason}, url={url})"
            )

        return result_page, success

    async def _ensure_tab_target(browser, page, url, wid, timeout=60):
        return await _ensure_tab(browser, page, url, wid, timeout, "target_page_intent")

    async def _ensure_tab_ad(browser, page, url, wid, timeout=60):
        return await _ensure_tab(browser, page, url, wid, timeout, "ad_landing_intent")

    async def _check_vignette(page, wid):
        await try_dismiss_consent(page, wid)
        return await check_and_handle_vignette(page, wid, extract_domain)

    async def _smart_click(
        page, wid, domain, element=None, is_ad=False, interaction_state=None
    ):
        return await smart_click(page, wid, domain, element, is_ad, interaction_state)

    async def _perform_activity(
        page, browser, wid, stay_time, is_ads=False, interaction_state=None,
        target_url=None,
    ):
        ensure_tab_fn = _ensure_tab_ad if is_ads else _ensure_tab_target

        ads_fn = None
        if is_ads and interaction_state is not None:
            async def _dispatch_ads(p, b, w, edf, max_duration=0):
                return await dispatch_ad_interaction(
                    p, b, w, edf, ctx.config, interaction_state, max_duration
                )
            ads_fn = _dispatch_ads

        return await perform_random_activity(
            page,
            browser,
            wid,
            stay_time,
            ctx.config,
            ctx.running,
            ensure_tab_fn,
            _smart_click,
            extract_domain,
            _check_vignette,
            is_ads,
            interaction_state,
            target_url if not is_ads else None,
            interact_with_ads_fn=ads_fn,
        )

    try:
        if not ctx.config["urls"]:
            print(f"Worker {worker_id}: No URLs configured")
            return

        while ctx.running:
            session_start_time = time.time()
            redirect_budget_states.clear()

            if (
                ctx.config["session"]["enabled"]
                and ctx.config["session"]["count"] > 0
                and session_count >= ctx.config["session"]["count"]
            ):
                print(f"Worker {worker_id}: Session count limit reached")
                break

            # Determine if this is an ads session (per-session probability)
            ads_ctr = ctx.config.get("ads", {}).get("ctr", 0)
            is_ads_session = random.random() * 100 < ads_ctr

            if is_ads_session:
                print(f"Worker {worker_id}: Starting AD INTERACTION session")
                ads_session_count += 1
            else:
                print(f"Worker {worker_id}: Starting normal session")

            session_count += 1
            session_id = f"w{worker_id}-s{session_count}-{int(time.time() * 1000)}"
            session_successful = False
            browser = None
            context = None
            is_persistent_context = False
            interaction_state = {"cursor_position": None}
            fingerprint_mode = "desktop"
            fallback_reason = ""

            # Hard session deadline — nothing runs past this
            session_max_seconds = ctx.config["session"]["max_time"] * 60 if ctx.config["session"]["max_time"] > 0 else 0
            session_deadline = (session_start_time + session_max_seconds) if session_max_seconds > 0 else 0

            def _session_remaining() -> float:
                """Seconds left in this session, or float('inf') if no limit."""
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
                    worker_id=worker_id,
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
                    ctx.config, worker_id, get_delay
                )
                if not browser_setup:
                    print(f"Worker {worker_id}: Failed to initialize browser")
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
                        f"Worker {worker_id}: Browser setup returned without browser instance"
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
                fallback_reason = str(browser_setup.get("fallback_reason", "") or "")
                emit_mobile_fingerprint_event(
                    worker_id=worker_id,
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
                    # CloakBrowser mobile: persistent context already created.
                    # Set browser = context so downstream code (ensure_correct_tab,
                    # activities, urls) can use it as the top-level object.
                    context = browser_setup.get("context")
                    browser = context
                    pages = context.pages
                    page = pages[0] if pages else await context.new_page()
                    print(
                        f"Worker {worker_id}: Using CloakBrowser persistent context"
                    )
                else:
                    # Camoufox desktop: create context from browser.
                    context_kwargs = dict(browser_setup.get("context_options") or {})
                    context = await browser.new_context(**context_kwargs)
                    page = await context.new_page()

                # Hoist random_navigation lambda outside URL loop — built once per session
                def _random_nav(p, wid, td):
                    return random_navigation(
                        p,
                        wid,
                        td,
                        _ensure_tab,
                        _smart_click,
                        accept_google_cookies,
                        _check_vignette,
                        ctx.config,
                    )

                # --- URL PROCESSING ---
                for url_index, url_data in enumerate(ctx.config["urls"]):
                    if not ctx.running:
                        break

                    if _session_expired():
                        print(f"Worker {worker_id}: Max session time reached ({session_max_seconds}s)")
                        break

                    if url_data["random_page"]:
                        urls = [
                            u.strip() for u in url_data["url"].split(",") if u.strip()
                        ]
                        url = random.choice(urls) if urls else url_data["url"].strip()
                    else:
                        url = url_data["url"].strip()

                    print(
                        f"Worker {worker_id}: [URL {url_index + 1}/{len(ctx.config['urls'])}] Visiting: {url}"
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
                            referrer = get_social_referrer()
                            if referrer:
                                await page.set_extra_http_headers({"referer": referrer})
                                print(
                                    f"Worker {worker_id}: Using social referrer: {referrer}"
                                )
                            print(f"Worker {worker_id}: Loading initial URL directly")
                            try:
                                await page.goto(
                                    url, timeout=30000, wait_until="domcontentloaded"
                                )
                            except Exception as e:
                                print(
                                    f"Worker {worker_id}: Error visiting URL: {str(e)}"
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
                                print(f"Worker {worker_id}: No valid keyword available")
                                raise SessionFailedException(
                                    "No valid keyword available"
                                )
                            print(f"Worker {worker_id}: Using keyword: {keyword}")
                            target_domain = extract_domain(url)
                            if not await perform_organic_search(
                                page,
                                keyword,
                                target_domain,
                                worker_id,
                                ctx.config,
                                extract_domain,
                            ):
                                print(f"Worker {worker_id}: Organic search failed")
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
                            print(f"Worker {worker_id}: Loading initial URL directly")
                            try:
                                await page.goto(
                                    url, timeout=30000, wait_until="domcontentloaded"
                                )
                            except Exception as e:
                                print(
                                    f"Worker {worker_id}: Error visiting URL: {str(e)}"
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
                        print(f"Worker {worker_id}: Navigating to next URL in sequence")
                        try:
                            await navigate_to_url_by_click(
                                page,
                                url,
                                worker_id,
                                _ensure_tab,
                                _smart_click,
                                accept_google_cookies,
                                _check_vignette,
                                _random_nav,
                                ctx.config,
                            )
                        except SessionFailedException:
                            print(
                                f"Worker {worker_id}: Falling back to direct navigation"
                            )
                            try:
                                await page.goto(
                                    url, timeout=30000, wait_until="domcontentloaded"
                                )
                            except Exception as e:
                                print(
                                    f"Worker {worker_id}: Error visiting URL: {str(e)}"
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

                    # Re-anchor immediately after URL load/click navigation.
                    page, success = await _ensure_tab_target(
                        browser, page, url, worker_id, timeout=25
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

                    # Page health check — detect error/timeout/proxy failures early
                    health = await check_page_health(page)
                    if not health.get("healthy", True):
                        reason = health.get("reason", "unknown")
                        print(f"Worker {worker_id}: Page unhealthy after navigation: {reason}")
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

                    page, success = await _ensure_tab_target(
                        browser, page, url, worker_id, timeout=20
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
                        page, worker_id, max_wait_seconds=gdpr_max_wait
                    )
                    consent_status = consent_result.get("status")
                    if consent_status == "unresolved":
                        print(
                            f"Worker {worker_id}: Consent unresolved "
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
                                f"Worker {worker_id}: Skipping URL due to unresolved consent"
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

                    page, success = await _ensure_tab_target(
                        browser, page, url, worker_id, timeout=20
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

                    await _check_vignette(page, worker_id)

                    page, success = await _ensure_tab_target(
                        browser, page, url, worker_id, timeout=20
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

                    # Check session deadline before committing to stay time
                    if _session_expired():
                        print(f"Worker {worker_id}: Session deadline reached before activity loop")
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

                    # Cap stay_time to session remaining time
                    remaining_budget = _session_remaining()
                    if remaining_budget < float("inf") and stay_time > remaining_budget:
                        stay_time = max(1, int(remaining_budget))

                    print(
                        f"Worker {worker_id}: Staying on page for {stay_time} seconds"
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

                        await _perform_activity(
                            page,
                            browser,
                            worker_id,
                            remaining_time,
                            is_ads_session,
                            interaction_state,
                            target_url=url,
                        )

                        # Recalculate after activity so delay uses fresh time
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
                        successful_ads_sessions += 1
                        _emit_step("ad_click", "ok", reason_code="ad_clicked_during_activity")
                    else:
                        _emit_step("ad_click", "failed", reason_code="no_ad_click_during_session")

                session_successful = True

                # Enforce minimum session duration if configured
                session_min_seconds = ctx.config.get("session", {}).get("min_time", 0) * 60
                if session_min_seconds > 0:
                    elapsed = time.time() - session_start_time
                    remaining_min = session_min_seconds - elapsed
                    if remaining_min > 1:
                        print(f"Worker {worker_id}: Session completed early, padding {int(remaining_min)}s to meet min_time")
                        await asyncio.sleep(remaining_min)

            except SessionFailedException as e:
                print(f"Worker {worker_id}: Session marked as failed: {str(e)}")
                _emit_step(
                    "session", "failed", reason_code="session_failed_exception", error=e
                )
                session_successful = False
            except Exception as e:
                print(f"Worker {worker_id}: Critical error: {str(e)}")
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
                            context, worker_id, ctx.config, _perform_activity, get_delay
                        )
                        await natural_exit(context, worker_id, get_delay)
                    if is_persistent_context and context:
                        await cleanup_browser(None, worker_id, context=context)
                    elif browser:
                        await cleanup_browser(browser, worker_id)
                except Exception as e:
                    print(f"Worker {worker_id}: Error during cleanup: {str(e)}")

                await asyncio.sleep(1)

            if session_successful:
                successful_sessions += 1
                consecutive_failures = 0
                delay = get_delay(10, 30)
                print(f"Worker {worker_id}: Session successful, waiting {delay}s")
                _emit_step("session", "ok", reason_code="session_completed")
            else:
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(
                        f"Worker {worker_id}: {consecutive_failures} consecutive failures, "
                        f"killing orphan browsers and cooling down {FAILURE_COOLDOWN_SECONDS}s"
                    )
                    _kill_child_browser_processes(worker_id)
                    _emit_step(
                        "session", "failed",
                        reason_code="consecutive_failure_cooldown",
                        meta={"consecutive_failures": consecutive_failures},
                    )
                    consecutive_failures = 0
                    await asyncio.sleep(FAILURE_COOLDOWN_SECONDS)
                    continue
                delay = get_delay(30, 60)
                print(f"Worker {worker_id}: Session failed, waiting {delay}s")

            emit_mobile_fingerprint_event(
                worker_id=worker_id,
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

            emit_heartbeat(worker_id, session_count, successful_sessions)

            await asyncio.sleep(delay)

    except Exception as e:
        print(f"Worker {worker_id}: FATAL ERROR: {str(e)}")
        _kill_child_browser_processes(worker_id)
    finally:
        # Write stats back to shared Manager dicts
        ctx.session_counts[worker_id] = session_count
        ctx.successful_sessions[worker_id] = successful_sessions
        ctx.ads_session_counts[worker_id] = ads_session_count
        ctx.successful_ads_sessions[worker_id] = successful_ads_sessions

        print(
            f"Worker {worker_id}: Session completed - "
            f"Total: {session_count}, "
            f"Success: {successful_sessions}, "
            f"Ads: {ads_session_count} ({successful_ads_sessions} successful), "
            f"RedirectRecoveries: {redirect_recoveries}"
        )


async def run_worker_async(
    config_path: str,
    worker_id: int,
    pending_ads_sessions,
    session_counts,
    successful_sessions,
    ads_session_counts,
    successful_ads_sessions,
):
    """Top-level async entry point for a multiprocessing worker."""
    import json

    try:
        with open(config_path, "r") as f:
            config = json.load(f)

        ctx = WorkerContext(
            config=config,
            running=True,
            pending_ads_sessions=pending_ads_sessions,
            session_counts=session_counts,
            successful_sessions=successful_sessions,
            ads_session_counts=ads_session_counts,
            successful_ads_sessions=successful_ads_sessions,
        )
        await worker_session(ctx, worker_id)
    except Exception as e:
        print(f"Worker {worker_id} failed: {str(e)}")


def run_worker(
    config_path: str,
    worker_id: int,
    pending_ads_sessions,
    session_counts,
    successful_sessions,
    ads_session_counts,
    successful_ads_sessions,
):
    """Wrapper to run async worker in a fresh event loop (called by multiprocessing)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(
        run_worker_async(
            config_path,
            worker_id,
            pending_ads_sessions,
            session_counts,
            successful_sessions,
            ads_session_counts,
            successful_ads_sessions,
        )
    )
    loop.close()
