"""
nexads/navigation/consent.py
Universal consent dialog detection and interaction helpers.
"""

from __future__ import annotations

import asyncio
import random
import time

from app.browser.humanization import gaussian_ms


CONSENT_DIALOG_SELECTORS = [
    'div.fc-dialog-container',
    'div[role="dialog"]',
    'div[class*="cookie"]',
    'div[class*="consent"]',
    'div[class*="gdpr"]',
    'div[class*="privacy"]',
    'div[id*="cookie"]',
    'div[id*="consent"]',
]

CONSENT_BUTTON_SELECTORS = [
    'button:has-text("Accept all")',
    'button:has-text("Accept")',
    'button:has-text("I agree")',
    'button:has-text("Agree")',
    'button:has-text("Consent")',
    'button:has-text("Continue")',
    'button:has-text("OK")',
    'button#L2AGLb',
    'button#accept-cookies',
    'button#consent-button',
    'p.fc-button-label:has-text("Consent")',
]


async def _find_visible_element(page, selectors: list[str], root=None):
    """Return first visible element matching selectors."""
    for selector in selectors:
        try:
            candidate = (
                await root.query_selector(selector)
                if root is not None
                else await page.query_selector(selector)
            )
            if candidate and await candidate.is_visible():
                return candidate, selector
        except Exception:
            continue
    return None, None


async def _is_any_dialog_visible(page) -> bool:
    """Return True when a consent-like dialog is currently visible."""
    for selector in CONSENT_DIALOG_SELECTORS:
        try:
            element = await page.query_selector(selector)
            if element and await element.is_visible():
                return True
        except Exception:
            continue
    return False


async def _probe_interceptor(page, target_box: dict) -> dict:
    """Inspect point-overlap and report potential pointer-event interceptor."""
    x = target_box['x'] + target_box['width'] / 2
    y = target_box['y'] + target_box['height'] / 2

    try:
        info = await page.evaluate(
            """
            ([x, y]) => {
                const top = document.elementFromPoint(x, y);
                if (!top) {
                    return { intercepted: false };
                }
                return {
                    intercepted: true,
                    tag: top.tagName || '',
                    id: top.id || '',
                    className: top.className || '',
                    href: top.getAttribute ? (top.getAttribute('href') || '') : ''
                };
            }
            """,
            [x, y],
        )
        if not isinstance(info, dict):
            return {"intercepted": False}
        return info
    except Exception:
        return {"intercepted": False}


async def _click_with_fallbacks(page, element, box: dict) -> tuple[bool, str]:
    """Attempt click with increasingly forceful fallback strategies."""
    x = box['x'] + box['width'] / 2
    y = box['y'] + box['height'] / 2
    delay = gaussian_ms(105, 28, 45, 220)

    strategies = [
        "native",
        "force",
        "mouse",
        "js",
    ]

    for strategy in strategies:
        try:
            if strategy == "native":
                await element.click(timeout=3500, delay=delay)
            elif strategy == "force":
                await element.click(timeout=3500, force=True, delay=delay)
            elif strategy == "mouse":
                await page.mouse.move(x, y, steps=random.randint(4, 9))
                await page.wait_for_timeout(gaussian_ms(180, 60, 90, 360))
                await page.mouse.click(x, y, delay=delay)
            else:
                await page.evaluate("(el) => el.click()", element)

            return True, strategy
        except Exception:
            continue

    return False, "none"


async def handle_consent_dialog(page, worker_id: int, max_wait_seconds: int = 12) -> dict:
    """Resolve consent dialogs in a universal way.

    Returns:
      {
        "status": "resolved|unresolved|not_present",
        "reason": str,
        "attempts": int
      }
    """
    start_time = time.time()
    attempts = 0
    saw_dialog = False

    while time.time() - start_time < max(1, max_wait_seconds):
        dialog, dialog_selector = await _find_visible_element(page, CONSENT_DIALOG_SELECTORS)
        if not dialog:
            if saw_dialog:
                return {"status": "resolved", "reason": "dialog_closed", "attempts": attempts}
            return {"status": "not_present", "reason": "dialog_not_found", "attempts": attempts}

        saw_dialog = True
        print(f"Worker {worker_id}: Consent dialog detected via {dialog_selector}")

        # Prefer buttons inside dialog, then fallback to global lookup.
        button, button_selector = await _find_visible_element(page, CONSENT_BUTTON_SELECTORS, root=dialog)
        if not button:
            button, button_selector = await _find_visible_element(page, CONSENT_BUTTON_SELECTORS)

        if not button:
            attempts += 1
            await asyncio.sleep(min(0.8, max(0.2, random.random() * 0.7 + 0.1)))
            continue

        try:
            await button.scroll_into_view_if_needed(timeout=4500)
        except Exception:
            pass

        box = await button.bounding_box()
        if not box:
            attempts += 1
            await asyncio.sleep(0.35)
            continue

        interceptor = await _probe_interceptor(page, box)
        if interceptor.get("intercepted"):
            tag = interceptor.get("tag", "")
            href = interceptor.get("href", "")
            print(
                f"Worker {worker_id}: Consent click interception risk "
                f"(top={tag}, href={href[:80]})"
            )

        clicked, strategy = await _click_with_fallbacks(page, button, box)
        attempts += 1
        if not clicked:
            await asyncio.sleep(0.4)
            continue

        print(
            f"Worker {worker_id}: Consent click success using {strategy} "
            f"({button_selector})"
        )

        await page.wait_for_timeout(gaussian_ms(420, 120, 180, 900))
        if not await _is_any_dialog_visible(page):
            return {"status": "resolved", "reason": f"clicked_{strategy}", "attempts": attempts}

        await asyncio.sleep(min(0.9, max(0.2, random.random() * 0.7 + 0.1)))

    return {"status": "unresolved", "reason": "timeout", "attempts": attempts}
