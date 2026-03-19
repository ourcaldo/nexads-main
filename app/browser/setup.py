"""
app/browser/setup.py
Browser initialization orchestrator.
Delegates to desktop.py (Camoufox) or mobile.py (Patchright) based on device type.
"""

import random

from app.browser.proxy import resolve_proxy_config
from app.browser.desktop import launch_desktop_browser, cleanup_desktop_browser
from app.browser.mobile import configure_mobile_browser, cleanup_mobile_context


async def configure_browser(config: dict, worker_id: int, get_random_delay_fn):
    """Configure and return browser setup result for one worker session."""
    try:
        proxy_cfg = resolve_proxy_config(config)

        headless = True
        if config["browser"]["headless_mode"] == "False":
            headless = False
        elif config["browser"]["headless_mode"] == "virtual":
            headless = "virtual"

        device_type = random.choices(
            ["mobile", "desktop"],
            weights=[config["device_type"]["mobile"], config["device_type"]["desktop"]],
            k=1,
        )[0]

        # Desktop path: Camoufox.
        if device_type != "mobile":
            return await launch_desktop_browser(
                config, headless, proxy_cfg, worker_id, get_random_delay_fn,
            )

        # Mobile path: Patchright + BrowserForge fingerprint.
        result = await configure_mobile_browser(
            config, headless, proxy_cfg, worker_id, get_random_delay_fn,
        )

        # If mobile fingerprint preflight failed, fallback to desktop.
        if result is None:
            print(
                f"Worker {worker_id}: Mobile fingerprint preflight failed, "
                f"continuing desktop flow"
            )
            return await launch_desktop_browser(
                config, headless, proxy_cfg, worker_id, get_random_delay_fn,
            )

        return result

    except Exception as e:
        print(f"Worker {worker_id}: Browser initialization error: {str(e)}")
        return None


async def cleanup_browser(browser, worker_id: int, context=None):
    """Clean up browser. Delegates to desktop or mobile cleanup."""
    try:
        if context is not None:
            await cleanup_mobile_context(context, worker_id)
            return

        await cleanup_desktop_browser(browser, worker_id)

    except Exception as e:
        print(f"Worker {worker_id}: Error during browser cleanup: {str(e)}")
