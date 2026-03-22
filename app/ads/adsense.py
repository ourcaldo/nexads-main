"""
nexads/ads/adsense.py
AdSense ad detection, interaction, and vignette handling.
"""

from __future__ import annotations

import asyncio
import random
import time

from app.ads.outcomes import evaluate_ad_click_outcome, persist_ad_click_event
from app.ads.signals import load_adsense_cosmetic_selectors
from app.browser.click import smart_click
from app.core.timings import timing_ms, timing_seconds


_DEFAULT_AD_SELECTORS = [
    'ins.adsbygoogle',
    'ins[class*="adsbygoogle"]',
    'div[id*="google_ads"]',
    'div[data-ad-client]',
    'div[data-ad-slot]',
    'div[class*="adsense"]',
]

_RUNTIME_AD_SELECTORS: list[str] | None = None


def _get_runtime_ad_selectors() -> list[str]:
    """Return merged default + EasyList-derived selectors, loaded once per process."""
    global _RUNTIME_AD_SELECTORS
    if _RUNTIME_AD_SELECTORS is not None:
        return _RUNTIME_AD_SELECTORS

    dynamic_selectors = load_adsense_cosmetic_selectors(limit=260)
    merged: list[str] = []
    seen: set[str] = set()

    for selector in _DEFAULT_AD_SELECTORS + dynamic_selectors:
        clean = selector.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        merged.append(clean)

    _RUNTIME_AD_SELECTORS = merged
    print(
        f"Ad selectors loaded: {len(_DEFAULT_AD_SELECTORS)} default + "
        f"{max(0, len(merged) - len(_DEFAULT_AD_SELECTORS))} dynamic"
    )
    return _RUNTIME_AD_SELECTORS


async def _has_rendered_content(element) -> bool:
    """Check if an ad container has actually rendered content, not just an empty placeholder."""
    try:
        return await element.evaluate("""(el) => {
            const tag = el.tagName.toUpperCase();

            // Helper: check if an iframe is a real ad creative (not a tracking pixel)
            const isAdCreativeIframe = (iframe) => {
                const src = iframe.src || '';
                const id = iframe.id || '';

                // Must have a Google ad-related src
                const hasAdSrc = src.includes('googleads') || src.includes('doubleclick') ||
                                 src.includes('googlesyndication') || src.includes('adservice.google');
                if (!hasAdSrc) return false;

                // Must have real ad dimensions (tracking iframes can be large but usually thin)
                const rect = iframe.getBoundingClientRect();
                if (rect.width < 50 || rect.height < 30) return false;

                // Known ad creative iframe ID patterns
                if (id.startsWith('aswift_') || id.startsWith('google_ads_iframe_')) return true;

                // Check if iframe has an ancestor ins[data-ad-status="filled"]
                let parent = iframe.parentElement;
                while (parent) {
                    if (parent.tagName === 'INS' && parent.getAttribute('data-ad-status') === 'filled') {
                        return true;
                    }
                    parent = parent.parentElement;
                }

                return false;
            };

            // Reject raw iframe elements — we only trust container-level detection
            if (tag === 'IFRAME') {
                return false;
            }

            // For INS elements, require data-ad-status === 'filled'
            if (tag === 'INS') {
                const status = el.getAttribute('data-ad-status');
                if (status !== 'filled') return false;
            }

            // Require a verified ad creative iframe child
            const iframes = el.querySelectorAll('iframe');
            for (const iframe of iframes) {
                if (isAdCreativeIframe(iframe)) return true;
            }

            return false;
        }""")
    except Exception:
        return False


async def detect_adsense_ads(page):
    """Detect and return all visible AdSense ad elements on the current page."""
    try:
        ad_selectors = _get_runtime_ad_selectors()
        visible_ads = []
        candidates = 0

        for selector in ad_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    try:
                        if await element.is_visible():
                            box = await element.bounding_box()
                            if box and box['width'] >= 50 and box['height'] >= 30:
                                candidates += 1
                                if await _has_rendered_content(element):
                                    visible_ads.append(element)
                    except Exception:
                        continue
            except Exception:
                continue

        filtered = candidates - len(visible_ads)
        msg = f"Found {len(visible_ads)} rendered AdSense ads"
        if filtered > 0:
            msg += f" ({filtered} unrendered containers filtered)"
        print(msg)
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
            await page.wait_for_timeout(timing_ms("ad_vignette"))
            return True

        return False

    except Exception as e:
        print(f"Worker {worker_id}: Error checking/handling vignette: {str(e)}")
        return False


async def interact_with_ads(page, browser, worker_id: int, extract_domain_fn,
                            max_duration: float = 0) -> bool:
    """Click visible AdSense ads and prefer natural left-click behavior."""
    interact_start = time.time()
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
        if max_duration > 0 and (time.time() - interact_start) >= max_duration:
            print(f"Worker {worker_id}: Ad interaction time budget exhausted")
            break
        try:
            source_url = page.url
            current_domain = extract_domain_fn(source_url)
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
                outcome = await evaluate_ad_click_outcome(
                    page=page,
                    context=context,
                    source_url=source_url,
                    source_domain=current_domain,
                    tabs_before=tabs_before,
                )
                print(
                    f"Worker {worker_id}: Ad outcome type={outcome['outcome_type']}, "
                    f"class={outcome['classification']}, score={outcome['confidence_score']:.2f}, "
                    f"final={outcome['final_domain']}, reasons={outcome['reason_codes']}"
                )

                is_accepted = (
                    outcome['confidence_score'] >= 0.60
                    and outcome['classification'] != 'blocked_or_failed'
                )
                outcome['legacy_binary_success'] = is_accepted
                outcome['worker_id'] = worker_id

                persisted = persist_ad_click_event(outcome)
                if not persisted:
                    print(f"Worker {worker_id}: Warning - could not persist ad click outcome event")

                if is_accepted:
                    print(f"Worker {worker_id}: Ad click accepted by confidence threshold")
                    clicked = True
                    break

                print(f"Worker {worker_id}: Ad click not accepted by confidence threshold")
                await asyncio.sleep(timing_seconds("ad_retry"))

        except Exception as e:
            print(f"Worker {worker_id}: Error clicking visible ad: {str(e)}")
            await asyncio.sleep(timing_seconds("ad_retry"))
            continue

    return clicked
