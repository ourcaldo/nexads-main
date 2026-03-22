"""
nexads/navigation/tabs.py
Tab management: ensure correct tab is focused, process ad tabs, natural exit.
"""

import random
import asyncio
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.browser.humanization import clamp, lognormal_seconds
from app.navigation.urls import extract_domain


@dataclass
class NavigationIntent:
    """Intent model used by tab recovery guard."""
    expected_domain: str
    allowed_domain_suffixes: list[str] = field(default_factory=list)
    intent_type: str = "target_page_intent"
    created_at: float = field(default_factory=time.time)
    max_recovery_seconds: int = 60


def _normalize_domain(domain: str) -> str:
    """Normalize domain for reliable tab matching."""
    if not domain:
        return ""
    cleaned = domain.strip().lower()
    if cleaned.startswith("www."):
        cleaned = cleaned[4:]
    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[0]
    return cleaned


def _domain_from_url(url: str) -> str:
    """Extract and normalize hostname from a URL string."""
    return extract_domain(url)


def _domain_matches(candidate_url: str, target_domain: str) -> bool:
    """Return True only when candidate URL host matches target domain/subdomain."""
    candidate_domain = _domain_from_url(candidate_url)
    normalized_target = _normalize_domain(target_domain)
    if not candidate_domain or not normalized_target:
        return False
    return (
        candidate_domain == normalized_target
        or candidate_domain.endswith(f".{normalized_target}")
    )


def _intent_domain_matches(candidate_url: str, intent: NavigationIntent, fallback_domain: str) -> bool:
    """Return True when URL host matches expected domain or allowed suffixes for this intent."""
    candidate_domain = _domain_from_url(candidate_url)
    expected = _normalize_domain(intent.expected_domain or fallback_domain)
    if not candidate_domain or not expected:
        return False

    if candidate_domain == expected or candidate_domain.endswith(f".{expected}"):
        return True

    for suffix in intent.allowed_domain_suffixes:
        normalized_suffix = _normalize_domain(suffix)
        if not normalized_suffix:
            continue
        if candidate_domain == normalized_suffix or candidate_domain.endswith(f".{normalized_suffix}"):
            return True

    return False


def _intent_budget_limits(intent_type: str, budget_limits: dict | None) -> tuple[int, int]:
    """Resolve per-intent recovery and new-tab limits."""
    default_map = {
        "target_page_intent": (8, 2),
        "ad_landing_intent": (6, 3),
        "recovery_intent": (10, 3),
    }
    default_recoveries, default_new_tabs = default_map.get(intent_type, (8, 2))
    if not isinstance(budget_limits, dict):
        return default_recoveries, default_new_tabs

    max_recoveries = int(budget_limits.get("max_recoveries", default_recoveries))
    max_new_tabs = int(budget_limits.get("max_new_tabs", default_new_tabs))
    return max(1, max_recoveries), max(0, max_new_tabs)


async def ensure_correct_tab(browser, page, target_url: str, worker_id: int,
                             config: dict, timeout: int = 60,
                             intent: NavigationIntent | None = None,
                             budget_state: dict | None = None,
                             budget_limits: dict | None = None):
    """
    Ensure the correct tab is focused before performing activities.
    Returns (page, success) tuple.
    """
    if not config['browser'].get('prevent_redirects', True):
        if isinstance(budget_state, dict):
            budget_state["last_reason_code"] = "redirect_guard_disabled"
        return page, True

    target_domain = extract_domain(target_url)
    resolved_intent = intent or NavigationIntent(
        expected_domain=target_domain,
        intent_type="target_page_intent",
        max_recovery_seconds=timeout,
    )

    timeout = int(max(1, min(timeout, resolved_intent.max_recovery_seconds)))
    start_time = time.time()
    attempts = 0

    if isinstance(budget_state, dict):
        budget_state.setdefault("recoveries", 0)
        budget_state.setdefault("new_tab_openings", 0)
        budget_state.setdefault("last_reason_code", "")

    max_recoveries, max_new_tabs = _intent_budget_limits(resolved_intent.intent_type, budget_limits)

    def _set_reason(code: str):
        if isinstance(budget_state, dict):
            budget_state["last_reason_code"] = code

    async def _try_open_target(candidate_page, location_label: str) -> bool:
        """Try multiple navigation strategies on a page before giving up."""
        if not candidate_page:
            return False
        try:
            if candidate_page.is_closed():
                return False
        except Exception:
            return False

        last_error = None
        for wait_state in ("domcontentloaded", "load", "networkidle"):
            try:
                await candidate_page.goto(target_url, timeout=30000, wait_until=wait_state)
            except Exception as e:
                last_error = e

            try:
                await candidate_page.wait_for_timeout(1200)
            except Exception:
                pass

            try:
                current_url = candidate_page.url
            except Exception:
                current_url = ""

            if _intent_domain_matches(current_url, resolved_intent, target_domain):
                try:
                    await candidate_page.bring_to_front()
                except Exception:
                    pass
                print(
                    f"Worker {worker_id}: Recovered target URL in {location_label} "
                    f"(wait_until={wait_state}, intent={resolved_intent.intent_type})"
                )
                _set_reason("recovered")
                return True

        if last_error:
            _set_reason("target_goto_failed")
            print(f"Worker {worker_id}: Error loading target URL in {location_label}: {last_error}")
        return False

    while time.time() - start_time < timeout:
        attempts += 1

        if attempts > max_recoveries:
            _set_reason("redirect_budget_recoveries_exhausted")
            print(
                f"Worker {worker_id}: Recovery budget exhausted "
                f"(intent={resolved_intent.intent_type}, attempts={attempts-1}, max={max_recoveries})"
            )
            return None, False

        try:
            contexts = browser.contexts if hasattr(browser, 'contexts') else [browser]
            pages = []
            for context in contexts:
                try:
                    pages.extend(context.pages)
                except:
                    continue

            current_tab = page if page and not page.is_closed() else (pages[0] if pages else None)
            target_page = None

            for p in pages:
                try:
                    if not p.is_closed() and _intent_domain_matches(p.url, resolved_intent, target_domain):
                        target_page = p
                        break
                except:
                    continue

            if not target_page:
                # Target tab not found — reuse or open new
                if len(pages) <= 1:
                    if current_tab:
                        if isinstance(budget_state, dict):
                            budget_state["recoveries"] = int(budget_state.get("recoveries", 0)) + 1
                        recovered = await _try_open_target(current_tab, "current tab")
                        if recovered:
                            return current_tab, True

                context = contexts[0] if contexts else await browser.new_context()
                new_page = None
                try:
                    if isinstance(budget_state, dict):
                        if int(budget_state.get("new_tab_openings", 0)) >= max_new_tabs:
                            _set_reason("redirect_budget_new_tab_exhausted")
                            print(
                                f"Worker {worker_id}: New-tab recovery budget exhausted "
                                f"(intent={resolved_intent.intent_type}, max={max_new_tabs})"
                            )
                            await asyncio.sleep(1)
                            continue
                    new_page = await context.new_page()
                    if isinstance(budget_state, dict):
                        budget_state["recoveries"] = int(budget_state.get("recoveries", 0)) + 1
                        budget_state["new_tab_openings"] = int(budget_state.get("new_tab_openings", 0)) + 1
                except Exception as e:
                    _set_reason("new_tab_create_failed")
                    print(f"Worker {worker_id}: Failed to create new tab for recovery: {e}")

                if new_page:
                    try:
                        recovered = await _try_open_target(new_page, "new tab")
                        if recovered:
                            print(f"Worker {worker_id}: Opened target URL in new tab")
                            return new_page, True

                        if not new_page.is_closed():
                            await new_page.close()
                    except Exception as e:
                        _set_reason("new_tab_recovery_failed")
                        print(f"Worker {worker_id}: Failed to recover target in new tab: {e}")
                        try:
                            if new_page and not new_page.is_closed():
                                await new_page.close()
                        except Exception:
                            pass

                # Continue retry loop instead of failing immediately.
                await asyncio.sleep(1)
                continue

            else:
                if current_tab and target_page != current_tab:
                    await target_page.bring_to_front()
                    try:
                        await target_page.wait_for_load_state("networkidle", timeout=5000)
                    except:
                        pass
                    print(f"Worker {worker_id}: Focused on existing tab with {target_url}")
                _set_reason("focused_existing_target")
                return target_page, True

            await asyncio.sleep(1)

        except Exception as e:
            _set_reason("unexpected_tab_guard_error")
            print(f"Worker {worker_id}: Unexpected error in ensure_correct_tab: {e}")
            await asyncio.sleep(1)

    _set_reason("redirect_timeout")
    print(f"Worker {worker_id}: Timeout ensuring correct tab for {target_url}")
    return None, False


async def process_ads_tabs(browser_context, worker_id: int, config: dict,
                           perform_random_activity_fn, get_random_delay_fn):
    """Process any ad tabs that were opened during the session."""
    try:
        try:
            pages = browser_context.pages
        except AttributeError:
            print(f"Worker {worker_id}: No pages found in browser context - natural exit")
            return 0

        if len(pages) <= 1:
            return 0

        print(f"Worker {worker_id}: Processing {len(pages)-1} ad tabs")
        config_urls = []

        for url_data in config['urls']:
            if url_data['random_page']:
                urls = [u.strip() for u in url_data['url'].split(',')]
                config_urls.extend(urls)
            else:
                config_urls.append(url_data['url'].strip())

        ad_tabs_processed = 0

        for page in pages:
            try:
                if page.is_closed():
                    continue

                current_url = page.url
                if any(_domain_matches(current_url, extract_domain(url)) for url in config_urls):
                    continue

                ad_tabs_processed += 1
                print(f"Worker {worker_id}: Processing ad tab: {current_url}")

                min_ads = int(config['ads']['min_time'])
                max_ads = int(config['ads']['max_time'])
                if min_ads >= max_ads:
                    base_stay = float(min_ads)
                else:
                    base_stay = lognormal_seconds((min_ads + max_ads) / 2, 0.55, min_ads, max_ads)

                try:
                    content_height = await page.evaluate(
                        "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
                    )
                except Exception:
                    content_height = 1600

                height_factor = clamp(content_height / 2600, 0.65, 2.1)
                stay_time = int(round(clamp(base_stay * height_factor, 5, 120)))

                # Realistic quick bounce behavior on some ad landings.
                if random.random() < 0.18:
                    stay_time = int(round(lognormal_seconds(8, 0.45, 5, 15)))

                interaction_state = {"cursor_position": None}
                print(
                    f"Worker {worker_id}: Ad tab dwell target {stay_time}s "
                    f"(content_height={int(content_height)})"
                )

                start_time = time.time()
                while time.time() - start_time < stay_time:
                    remaining = max(0.0, stay_time - (time.time() - start_time))
                    if remaining <= 0:
                        break

                    await perform_random_activity_fn(
                        page, browser_context, worker_id, remaining, True, interaction_state
                    )

                    idle_delay = min(lognormal_seconds(1.5, 0.45, 0.7, 3.8), remaining)
                    if idle_delay > 0:
                        await asyncio.sleep(idle_delay)

                await page.close()

            except Exception as e:
                print(f"Worker {worker_id}: Error processing ad tab: {str(e)}")
                continue

        return ad_tabs_processed

    except Exception as e:
        print(f"Worker {worker_id}: Error processing ad tabs: {str(e)}")
        return 0


async def natural_exit(browser_context, worker_id: int, get_random_delay_fn):
    """Perform varied, human-like session exit behavior."""
    try:
        try:
            pages = browser_context.pages
        except AttributeError:
            print(f"Worker {worker_id}: No pages found for natural exit")
            return False

        if not pages:
            return True

        print(f"Worker {worker_id}: Starting natural exit sequence")

        while len(pages) > 1:
            try:
                page = pages[-1]
                if not page.is_closed():
                    await page.close()
                pages = browser_context.pages
                await asyncio.sleep(get_random_delay_fn(1, 2))
            except Exception as e:
                print(f"Worker {worker_id}: Error closing tab during natural exit: {str(e)}")
                # Refresh page list and continue closing remaining tabs instead of breaking
                try:
                    pages = browser_context.pages
                except Exception:
                    break

        if pages:
            try:
                page = pages[0]
                if not page.is_closed():
                    exit_roll = random.random()
                    if exit_roll < 0.40:
                        strategy = "close_direct"
                    elif exit_roll < 0.60:
                        strategy = "google"
                    elif exit_roll < 0.75:
                        strategy = "random_site"
                    elif exit_roll < 0.90:
                        strategy = "new_tab"
                    else:
                        strategy = "linger"

                    print(f"Worker {worker_id}: Exit strategy = {strategy}")

                    if strategy == "google":
                        await page.goto("https://www.google.com", timeout=45000, wait_until="networkidle")
                        await asyncio.sleep(lognormal_seconds(2.5, 0.45, 1.2, 6.0))
                    elif strategy == "random_site":
                        site = random.choice([
                            "https://duckduckgo.com/",
                            "https://www.bing.com/",
                            "https://news.ycombinator.com/",
                            "https://www.wikipedia.org/",
                            "https://www.reddit.com/",
                        ])
                        await page.goto(site, timeout=45000, wait_until="networkidle")
                        await asyncio.sleep(lognormal_seconds(2.2, 0.45, 1.0, 5.5))
                    elif strategy == "new_tab":
                        await page.goto("about:blank", timeout=20000, wait_until="domcontentloaded")
                        await asyncio.sleep(lognormal_seconds(1.4, 0.4, 0.5, 3.0))
                    elif strategy == "linger":
                        if random.random() < 0.55:
                            await page.mouse.wheel(0, int(random.gauss(220, 90)))
                        await asyncio.sleep(lognormal_seconds(2.8, 0.5, 1.2, 7.0))
                    else:
                        await asyncio.sleep(lognormal_seconds(1.2, 0.4, 0.5, 3.0))

                    await page.close()
            except Exception as e:
                print(f"Worker {worker_id}: Error during natural exit strategy: {str(e)}")

        return True

    except Exception as e:
        print(f"Worker {worker_id}: Error during natural exit: {str(e)}")
        return False
