"""
nexads/ads/adsterra.py
Adsterra ad detection, interaction, and click handling.
"""

import asyncio
import random
import time

from app.ads.outcomes import evaluate_ad_click_outcome, persist_ad_click_event
from app.ads.adsense import smart_click
from app.browser.humanization import lognormal_seconds

# Known Adsterra tracking/serving domains
_ADSTERRA_DOMAINS = [
    "sourshaped.com",
    "skinnycrawlinglax.com",
    "wayfarerorthodox.com",
    "realizationnewestfangs.com",
]

# Adsterra ads use atContainer-{hash} / atLink-{hash} DOM pattern
_ADSTERRA_SELECTORS = [
    'div[id^="atContainer-"]',                     # Primary: Adsterra ad container
    'a[id^="atLink-"]',                            # Direct link element
    *[f'iframe[src*="{d}"]' for d in _ADSTERRA_DOMAINS],  # Fallback: iframe format
]

# Known Adsterra image CDN and redirect domains
_ADSTERRA_CONTENT_DOMAINS = [
    "storageimagedisplay.com",
    *_ADSTERRA_DOMAINS,
]


async def _has_adsterra_content(element) -> bool:
    """Check if an Adsterra ad element has actually rendered content."""
    try:
        return await element.evaluate("""(el) => {
            const tag = el.tagName.toUpperCase();

            // Direct iframe format (fallback)
            if (tag === 'IFRAME') {
                const rect = el.getBoundingClientRect();
                return rect.width >= 50 && rect.height >= 30;
            }

            // atContainer or atLink format: look for <a> with <img> inside
            const link = (tag === 'A') ? el : el.querySelector('a[id^="atLink-"]');
            if (link) {
                const img = link.querySelector('img');
                if (img) {
                    const rect = img.getBoundingClientRect();
                    return rect.width >= 30 && rect.height >= 30;
                }
            }

            // Generic: any visible image child with real dimensions
            const imgs = el.querySelectorAll('img');
            for (const img of imgs) {
                const rect = img.getBoundingClientRect();
                if (rect.width >= 30 && rect.height >= 30) return true;
            }

            return false;
        }""")
    except Exception:
        return False


async def detect_adsterra_ads(page):
    """Detect and return all visible Adsterra ad elements on the current page."""
    try:
        visible_ads = []
        candidates = 0

        for selector in _ADSTERRA_SELECTORS:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    try:
                        if await element.is_visible():
                            box = await element.bounding_box()
                            if box and box['width'] >= 50 and box['height'] >= 30:
                                candidates += 1
                                if await _has_adsterra_content(element):
                                    visible_ads.append(element)
                    except Exception:
                        continue
            except Exception:
                continue

        filtered = candidates - len(visible_ads)
        msg = f"Found {len(visible_ads)} rendered Adsterra ads"
        if filtered > 0:
            msg += f" ({filtered} unrendered containers filtered)"
        print(msg)
        return visible_ads

    except Exception as e:
        print(f"Adsterra detection error: {str(e)}")
        return []


async def interact_with_adsterra_ads(page, browser, worker_id: int, extract_domain_fn,
                                     max_duration: float = 0) -> bool:
    """Click visible Adsterra ads and evaluate outcomes."""
    interact_start = time.time()
    visible_ads = await detect_adsterra_ads(page)
    if not visible_ads:
        print(f"Worker {worker_id}: No visible Adsterra ads found on page")
        return False

    print(f"Worker {worker_id}: Found {len(visible_ads)} visible Adsterra ads on page")

    context = page.context
    tabs_before = len(context.pages)
    clicked = False
    interaction_state: dict = {}

    random.shuffle(visible_ads)

    for ad in visible_ads:
        if max_duration > 0 and (time.time() - interact_start) >= max_duration:
            print(f"Worker {worker_id}: Adsterra interaction time budget exhausted")
            break
        try:
            source_url = page.url
            current_domain = extract_domain_fn(source_url)

            # Resolve clickable element: prefer <a> link inside container
            click_target = ad
            tag = await ad.evaluate("el => el.tagName.toUpperCase()")
            if tag != "A":
                link = await ad.query_selector('a[id^="atLink-"]')
                if not link:
                    link = await ad.query_selector("a[href]")
                if link:
                    click_target = link

            box = await click_target.bounding_box()
            ad_position = f"({box['x']:.0f},{box['y']:.0f})" if box else "(unknown position)"
            print(f"Worker {worker_id}: Attempting to click Adsterra ad at {ad_position}")

            if await smart_click(
                page, worker_id, current_domain, click_target,
                is_ad_activity=True, interaction_state=interaction_state,
            ):
                outcome = await evaluate_ad_click_outcome(
                    page=page, context=context,
                    source_url=source_url, source_domain=current_domain,
                    tabs_before=tabs_before, monitor_seconds=5.0,
                )
                print(
                    f"Worker {worker_id}: Adsterra outcome type={outcome['outcome_type']}, "
                    f"class={outcome['classification']}, score={outcome['confidence_score']:.2f}, "
                    f"final={outcome['final_domain']}, reasons={outcome['reason_codes']}"
                )

                is_accepted = (
                    outcome['confidence_score'] >= 0.60
                    and outcome['classification'] != 'blocked_or_failed'
                )
                outcome['legacy_binary_success'] = is_accepted
                outcome['worker_id'] = worker_id
                outcome['ad_provider'] = 'adsterra'

                persisted = persist_ad_click_event(outcome)
                if not persisted:
                    print(f"Worker {worker_id}: Warning - could not persist Adsterra ad click event")

                if is_accepted:
                    print(f"Worker {worker_id}: Adsterra ad click accepted")
                    clicked = True
                    break

                print(f"Worker {worker_id}: Adsterra ad click not accepted")
                await asyncio.sleep(lognormal_seconds(0.8, 0.4, 0.35, 2.0))

        except Exception as e:
            print(f"Worker {worker_id}: Error clicking Adsterra ad: {str(e)}")
            await asyncio.sleep(lognormal_seconds(0.8, 0.4, 0.35, 2.0))
            continue

    return clicked
