"""
nexads/ads/adsterra.py
Adsterra ad detection, interaction, and click handling.
Supports direct DOM, cross-origin iframe, and external-URL fallback detection.
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

# Known Adsterra ad iframe host domains (publisher-managed)
_ADSTERRA_IFRAME_HOSTS = [
    "alco.camarjaya.co.id",
    "elco.camarjaya.co.id",
]

# Selectors for direct-DOM Adsterra elements (non-iframed)
_ADSTERRA_DIRECT_SELECTORS = [
    'div[id^="atContainer-"]',
    'a[id^="atLink-"]',
]


async def _detect_direct_ads(page, worker_id: int) -> list:
    """Layer 1: Detect Adsterra ads in the top-level page DOM."""
    visible_ads = []
    for selector in _ADSTERRA_DIRECT_SELECTORS:
        try:
            elements = await page.query_selector_all(selector)
            for element in elements:
                try:
                    if await element.is_visible():
                        box = await element.bounding_box()
                        if box and box['width'] >= 30 and box['height'] >= 30:
                            visible_ads.append({"element": element, "frame": None, "source": "direct"})
                except Exception:
                    continue
        except Exception:
            continue
    return visible_ads


async def _detect_iframe_ads(page, worker_id: int) -> list:
    """Layer 2: Detect Adsterra ads inside known publisher ad iframes."""
    visible_ads = []

    for host in _ADSTERRA_IFRAME_HOSTS:
        try:
            iframes = await page.query_selector_all(f'iframe[src*="{host}"]')
            for iframe_el in iframes:
                try:
                    if not await iframe_el.is_visible():
                        continue
                    box = await iframe_el.bounding_box()
                    if not box or box['width'] < 30 or box['height'] < 30:
                        continue

                    frame = await iframe_el.content_frame()
                    if not frame:
                        continue

                    # Look for atLink or any clickable link inside the iframe
                    link = await frame.query_selector('a[id^="atLink-"]')
                    if not link:
                        link = await frame.query_selector('a[href]')
                    if not link:
                        continue

                    # Verify the link has visible content (img or text)
                    has_content = await frame.evaluate("""() => {
                        const link = document.querySelector('a[href]');
                        if (!link) return false;
                        const img = link.querySelector('img');
                        if (img) {
                            const rect = img.getBoundingClientRect();
                            return rect.width >= 10 && rect.height >= 10;
                        }
                        return link.textContent.trim().length > 0;
                    }""")
                    if has_content:
                        visible_ads.append({
                            "element": link,
                            "frame": frame,
                            "source": f"iframe:{host}",
                        })
                except Exception:
                    continue
        except Exception:
            continue

    return visible_ads


async def _detect_external_url_ads(page, worker_id: int, site_domain: str) -> list:
    """Layer 3 (fallback): Find external links inside any iframe as potential ads."""
    visible_ads = []

    try:
        all_iframes = await page.query_selector_all("iframe")
        for iframe_el in all_iframes:
            try:
                if not await iframe_el.is_visible():
                    continue
                box = await iframe_el.bounding_box()
                if not box or box['width'] < 30 or box['height'] < 30:
                    continue

                frame = await iframe_el.content_frame()
                if not frame:
                    continue

                # Find external links in this iframe
                links_data = await frame.evaluate("""(siteDomain) => {
                    const results = [];
                    document.querySelectorAll('a[href]').forEach(a => {
                        const href = a.href || '';
                        if (!href || href.startsWith('javascript:')) return;
                        try {
                            const url = new URL(href);
                            const host = url.hostname.toLowerCase();
                            if (host && !host.includes(siteDomain)) {
                                const rect = a.getBoundingClientRect();
                                if (rect.width >= 10 && rect.height >= 10) {
                                    results.push({
                                        href: href,
                                        width: rect.width,
                                        height: rect.height,
                                    });
                                }
                            }
                        } catch(e) {}
                    });
                    return results;
                }""", site_domain)

                if not links_data:
                    continue

                # Get actual element handles for the external links
                for link_info in links_data:
                    try:
                        link_el = await frame.query_selector(f'a[href="{link_info["href"]}"]')
                        if not link_el:
                            # Try partial match for hrefs with special chars
                            all_links = await frame.query_selector_all("a[href]")
                            for candidate in all_links:
                                href = await candidate.get_attribute("href")
                                if href and link_info["href"] in href:
                                    link_el = candidate
                                    break
                        if link_el:
                            visible_ads.append({
                                "element": link_el,
                                "frame": frame,
                                "source": "external_url",
                                "href": link_info["href"],
                            })
                    except Exception:
                        continue

            except Exception:
                continue
    except Exception:
        pass

    return visible_ads


async def detect_adsterra_ads(page, worker_id: int = 0, site_domain: str = ""):
    """Detect Adsterra ads using three layers: direct DOM, iframe, external URL fallback."""
    try:
        # Layer 1: Direct DOM detection
        ads = await _detect_direct_ads(page, worker_id)
        if ads:
            print(f"Found {len(ads)} Adsterra ads (direct DOM)")
            return ads

        # Layer 2: Known iframe hosts
        ads = await _detect_iframe_ads(page, worker_id)
        if ads:
            print(f"Found {len(ads)} Adsterra ads (iframe: {_ADSTERRA_IFRAME_HOSTS})")
            return ads

        # Layer 3: External URL fallback
        if site_domain:
            ads = await _detect_external_url_ads(page, worker_id, site_domain)
            if ads:
                print(f"Found {len(ads)} potential ads (external URLs in iframes)")
                return ads

        print("Found 0 Adsterra ads (all layers checked)")
        return []

    except Exception as e:
        print(f"Adsterra detection error: {str(e)}")
        return []


async def _click_ad_element(page, ad_info: dict, worker_id: int,
                            extract_domain_fn, interaction_state: dict) -> bool:
    """Click an ad element, handling both top-level and iframe contexts."""
    element = ad_info["element"]
    source = ad_info.get("source", "unknown")

    try:
        box = await element.bounding_box()
        if not box or box['width'] < 10 or box['height'] < 10:
            return False

        ad_position = f"({box['x']:.0f},{box['y']:.0f})"
        print(f"Worker {worker_id}: Attempting to click Adsterra ad at {ad_position} (source={source})")

        current_domain = extract_domain_fn(page.url)

        # Always use the top-level page for smart_click (needs page.mouse, page.context).
        # Element handles from iframes still work — bounding_box() returns main-viewport coords.
        if await smart_click(
            page, worker_id, current_domain, element,
            is_ad_activity=True, interaction_state=interaction_state,
        ):
            return True

    except Exception as e:
        print(f"Worker {worker_id}: Error clicking Adsterra ad: {str(e)}")

    return False


async def interact_with_adsterra_ads(page, browser, worker_id: int, extract_domain_fn,
                                     max_duration: float = 0) -> bool:
    """Click visible Adsterra ads and evaluate outcomes."""
    interact_start = time.time()

    # Extract site domain for external URL fallback
    site_domain = extract_domain_fn(page.url)
    # Strip subdomain to get base domain for broader matching
    parts = site_domain.split(".")
    base_domain = ".".join(parts[-2:]) if len(parts) >= 2 else site_domain

    visible_ads = await detect_adsterra_ads(page, worker_id, base_domain)
    if not visible_ads:
        print(f"Worker {worker_id}: No visible Adsterra ads found on page")
        return False

    print(f"Worker {worker_id}: Found {len(visible_ads)} Adsterra ad(s) to try")

    context = page.context
    tabs_before = len(context.pages)
    clicked = False
    interaction_state: dict = {}

    random.shuffle(visible_ads)

    for ad_info in visible_ads:
        if max_duration > 0 and (time.time() - interact_start) >= max_duration:
            print(f"Worker {worker_id}: Adsterra interaction time budget exhausted")
            break
        try:
            source_url = page.url
            source_domain = extract_domain_fn(source_url)

            click_success = await _click_ad_element(
                page, ad_info, worker_id, extract_domain_fn, interaction_state
            )

            if click_success:
                outcome = await evaluate_ad_click_outcome(
                    page=page, context=context,
                    source_url=source_url, source_domain=source_domain,
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
                outcome['ad_source'] = ad_info.get("source", "unknown")

                persisted = persist_ad_click_event(outcome)
                if not persisted:
                    print(f"Worker {worker_id}: Warning - could not persist Adsterra ad click event")

                if is_accepted:
                    print(f"Worker {worker_id}: Adsterra ad click accepted (source={ad_info.get('source')})")
                    clicked = True
                    break

                print(f"Worker {worker_id}: Adsterra ad click not accepted")
                await asyncio.sleep(lognormal_seconds(0.8, 0.4, 0.35, 2.0))

        except Exception as e:
            print(f"Worker {worker_id}: Error in Adsterra ad interaction: {str(e)}")
            await asyncio.sleep(lognormal_seconds(0.8, 0.4, 0.35, 2.0))
            continue

    return clicked
