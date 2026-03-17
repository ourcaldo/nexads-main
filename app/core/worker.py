"""
nexads/core/worker.py
Worker session logic: WorkerContext, worker_session, run_worker, run_worker_async.
"""

import random
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app.browser.setup import configure_browser, cleanup_browser
from app.browser.activities import perform_random_activity
from app.navigation.urls import extract_domain, navigate_to_url_by_click, random_navigation
from app.navigation.referrer import (
    get_random_keyword, perform_organic_search,
    accept_google_cookies, handle_gdpr_consent, get_social_referrer
)
from app.navigation.tabs import ensure_correct_tab, process_ads_tabs, natural_exit
from app.ads.adsense import (
    interact_with_ads, check_and_handle_vignette, smart_click
)


@dataclass
class WorkerContext:
    """Shared state passed to every worker function."""
    config: dict
    running: bool
    pending_ads_sessions: object  # multiprocessing.Value proxy
    session_counts: object        # multiprocessing.Manager dict proxy
    successful_sessions: object   # multiprocessing.Manager dict proxy
    ads_session_counts: object    # multiprocessing.Manager dict proxy
    successful_ads_sessions: object  # multiprocessing.Manager dict proxy


class SessionFailedException(Exception):
    """Raised when a session cannot continue."""
    pass


async def worker_session(ctx: WorkerContext, worker_id: int):
    """Main worker loop: runs sessions until stopped or session limit reached."""
    session_count = 0
    successful_sessions = 0
    ads_session_count = 0
    successful_ads_sessions = 0

    # Build bound helpers that close over ctx
    def get_delay(min_t=None, max_t=None):
        min_val = min_t if min_t is not None else ctx.config['delay']['min_time']
        max_val = max_t if max_t is not None else ctx.config['delay']['max_time']
        return random.randint(min_val, max_val)

    async def _ensure_tab(browser, page, url, wid, timeout=60):
        return await ensure_correct_tab(browser, page, url, wid, ctx.config, timeout)

    async def _check_vignette(page, wid):
        return await check_and_handle_vignette(page, wid, extract_domain)

    async def _smart_click(page, wid, domain, element=None, is_ad=False):
        return await smart_click(page, wid, domain, element, is_ad)

    async def _perform_activity(page, browser, wid, stay_time, is_ads=False):
        return await perform_random_activity(
            page, browser, wid, stay_time, ctx.config, ctx.running,
            _ensure_tab, _smart_click, extract_domain, _check_vignette, is_ads
        )

    try:
        if not ctx.config['urls']:
            print(f"Worker {worker_id}: No URLs configured")
            return

        while ctx.running:
            session_start_time = time.time()

            if (ctx.config['session']['enabled'] and
                    ctx.config['session']['count'] > 0 and
                    session_count >= ctx.config['session']['count']):
                print(f"Worker {worker_id}: Session count limit reached")
                break

            # Determine if this is an ads session (single shared counter)
            is_ads_session = False
            if ctx.pending_ads_sessions.value > 0:
                ctx.pending_ads_sessions.value -= 1
                is_ads_session = True

            if is_ads_session:
                print(f"Worker {worker_id}: Starting AD INTERACTION session")
                ads_session_count += 1
            else:
                print(f"Worker {worker_id}: Starting normal session")

            session_count += 1
            session_successful = False
            browser = None
            context = None

            try:
                # --- BROWSER INIT ---
                browser = await configure_browser(ctx.config, worker_id, get_delay)
                if not browser:
                    print(f"Worker {worker_id}: Failed to initialize browser")
                    await asyncio.sleep(10)
                    continue

                context = await browser.new_context()
                page = await context.new_page()
                ad_click_success = False

                # Hoist random_navigation lambda outside URL loop — built once per session
                def _random_nav(p, wid, td):
                    return random_navigation(
                        p, wid, td, _ensure_tab, _smart_click,
                        accept_google_cookies, _check_vignette, ctx.config
                    )

                # --- URL PROCESSING ---
                for url_index, url_data in enumerate(ctx.config['urls']):
                    if not ctx.running:
                        break

                    if (ctx.config['session']['max_time'] > 0 and
                            (time.time() - session_start_time) >= ctx.config['session']['max_time'] * 60):  # max_time in minutes → convert to seconds
                        print(f"Worker {worker_id}: Max session time reached")
                        break

                    if url_data['random_page']:
                        urls = [u.strip() for u in url_data['url'].split(',') if u.strip()]
                        url = random.choice(urls) if urls else url_data['url'].strip()
                    else:
                        url = url_data['url'].strip()

                    print(f"Worker {worker_id}: [URL {url_index + 1}/{len(ctx.config['urls'])}] Visiting: {url}")

                    # --- FIRST URL ---
                    if url_index == 0:
                        referrer_types = ctx.config['referrer']['types']
                        referrer_type = random.choice(referrer_types)

                        if referrer_type == "social":
                            referrer = get_social_referrer()
                            if referrer:
                                await page.set_extra_http_headers({'referer': referrer})
                                print(f"Worker {worker_id}: Using social referrer: {referrer}")
                            print(f"Worker {worker_id}: Loading initial URL directly")
                            try:
                                await page.goto(url, timeout=90000, wait_until="networkidle")
                            except Exception as e:
                                print(f"Worker {worker_id}: Error visiting URL: {str(e)}")
                                raise SessionFailedException("Failed to visit initial URL")

                        elif referrer_type == "organic":
                            keyword = get_random_keyword(ctx.config)
                            if not keyword:
                                print(f"Worker {worker_id}: No valid keyword available")
                                raise SessionFailedException("No valid keyword available")
                            print(f"Worker {worker_id}: Using keyword: {keyword}")
                            target_domain = extract_domain(url)
                            if not await perform_organic_search(
                                    page, keyword, target_domain, worker_id, ctx.config, extract_domain):
                                print(f"Worker {worker_id}: Organic search failed")
                                raise SessionFailedException("Organic search failed")

                        else:
                            print(f"Worker {worker_id}: Loading initial URL directly")
                            try:
                                await page.goto(url, timeout=90000, wait_until="networkidle")
                            except Exception as e:
                                print(f"Worker {worker_id}: Error visiting URL: {str(e)}")
                                raise SessionFailedException("Failed to visit initial URL")

                    # --- SUBSEQUENT URLS ---
                    else:
                        print(f"Worker {worker_id}: Navigating to next URL in sequence")
                        try:
                            await navigate_to_url_by_click(
                                page, url, worker_id,
                                _ensure_tab, _smart_click,
                                accept_google_cookies, _check_vignette,
                                _random_nav,
                                ctx.config
                            )
                        except SessionFailedException:
                            print(f"Worker {worker_id}: Falling back to direct navigation")
                            try:
                                await page.goto(url, timeout=90000, wait_until="networkidle")
                            except Exception as e:
                                print(f"Worker {worker_id}: Error visiting URL: {str(e)}")
                                raise SessionFailedException("Failed to navigate to URL")

                    if ctx.config['browser']['auto_accept_cookies']:
                        await accept_google_cookies(page)

                    await handle_gdpr_consent(page, worker_id)
                    await _check_vignette(page, worker_id)

                    stay_time = random.randint(url_data['min_time'], url_data['max_time'])  # seconds
                    print(f"Worker {worker_id}: Staying on page for {stay_time} seconds")

                    activity_start = time.time()
                    remaining_time = stay_time
                    while remaining_time > 0 and ctx.running:
                        elapsed = time.time() - activity_start
                        remaining_time = stay_time - elapsed

                        await _perform_activity(
                            page, browser, worker_id, remaining_time, is_ads_session)

                        if remaining_time > 0:
                            delay = min(random.uniform(0.5, 1.5), remaining_time)
                            if delay > 0:
                                await asyncio.sleep(delay)

                    if is_ads_session and not ad_click_success:
                        print(f"Worker {worker_id}: Checking for ads elements on URL {url_index + 1}")
                        tabs_before = len(context.pages)
                        ad_click_success = await interact_with_ads(page, browser, worker_id, extract_domain)

                        if ad_click_success:
                            tabs_after = len(context.pages)
                            if tabs_after > tabs_before:
                                print(f"Worker {worker_id}: Ad click successful (new tab opened)")
                                successful_ads_sessions += 1
                            else:
                                print(f"Worker {worker_id}: Ad click did not open new tab")
                                ad_click_success = False

                session_successful = True

            except SessionFailedException as e:
                print(f"Worker {worker_id}: Session marked as failed: {str(e)}")
                session_successful = False
            except Exception as e:
                print(f"Worker {worker_id}: Critical error: {str(e)}")
                session_successful = False

            finally:
                try:
                    if browser and context:
                        await process_ads_tabs(
                            context, worker_id, ctx.config,
                            _perform_activity, get_delay
                        )
                        await natural_exit(context, worker_id, get_delay)
                        await cleanup_browser(browser, worker_id)
                    elif browser:
                        await cleanup_browser(browser, worker_id)
                except Exception as e:
                    print(f"Worker {worker_id}: Error during cleanup: {str(e)}")

                await asyncio.sleep(1)

            if session_successful:
                successful_sessions += 1
                delay = get_delay(10, 30)
                print(f"Worker {worker_id}: Session successful, waiting {delay}s")
            else:
                delay = get_delay(30, 60)
                print(f"Worker {worker_id}: Session failed, waiting {delay}s")

            await asyncio.sleep(delay)

    except Exception as e:
        print(f"Worker {worker_id}: FATAL ERROR: {str(e)}")
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
            f"Ads: {ads_session_count} ({successful_ads_sessions} successful)"
        )


async def run_worker_async(config_path: str, worker_id: int,
                           pending_ads_sessions, session_counts,
                           successful_sessions, ads_session_counts,
                           successful_ads_sessions):
    """Top-level async entry point for a multiprocessing worker."""
    import json
    try:
        with open(config_path, 'r') as f:
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


def run_worker(config_path: str, worker_id: int,
               pending_ads_sessions, session_counts,
               successful_sessions, ads_session_counts,
               successful_ads_sessions):
    """Wrapper to run async worker in a fresh event loop (called by multiprocessing)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(
        run_worker_async(config_path, worker_id,
                         pending_ads_sessions, session_counts,
                         successful_sessions, ads_session_counts,
                         successful_ads_sessions)
    )
    loop.close()
