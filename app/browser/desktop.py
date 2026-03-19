"""
app/browser/desktop.py
Desktop browser sessions using Camoufox (anti-detect Firefox).
"""

import random
import asyncio
from typing import Optional, Dict

from camoufox.async_api import AsyncCamoufox
from camoufox import DefaultAddons
from browserforge.fingerprints import Screen


async def launch_desktop_browser(
    config: dict,
    headless,
    proxy_cfg: Optional[Dict[str, str]],
    worker_id: int,
    get_random_delay_fn,
) -> dict:
    """Launch Camoufox for a desktop session.

    Returns setup_result dict with "browser" key set.
    """
    os_fingerprint = random.choice(config["os_fingerprint"])
    options = {
        "headless": headless,
        "os": os_fingerprint,
        "screen": Screen(max_width=1920, max_height=1080),
        "geoip": True,
        "humanize": True,
    }
    if config["browser"]["disable_ublock"]:
        options["exclude_addons"] = [DefaultAddons.UBO]
    if proxy_cfg:
        options["proxy"] = proxy_cfg

    browser = await AsyncCamoufox(**options).start()
    delay = get_random_delay_fn()
    await asyncio.sleep(delay)

    return {
        "browser": browser,
        "context": None,
        "context_options": {},
        "fingerprint_mode": "desktop",
        "fallback_reason": "",
        "validation_reason_codes": [],
        "is_persistent_context": False,
    }


async def cleanup_desktop_browser(browser, worker_id: int):
    """Close all Camoufox contexts and the browser."""
    if not browser:
        return

    for ctx in browser.contexts:
        try:
            await ctx.close()
        except Exception:
            pass

    try:
        await browser.close()
    except Exception:
        pass
