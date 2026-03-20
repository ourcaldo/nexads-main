"""
app/browser/mobile.py
Mobile browser sessions using CloakBrowser (stealth Chromium with source-level patches).
"""

import asyncio
import random
import shutil
import tempfile
from typing import Optional, Dict

from app.browser.proxy import build_full_proxy_url
from app.core.telemetry import emit_mobile_fingerprint_event

# Mobile device profile: Google Pixel 8 (Android 14)
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.7632.159 Mobile Safari/537.36"
)
MOBILE_VIEWPORT = {"width": 412, "height": 915}
MOBILE_DPR = 2.625

# CloakBrowser fingerprint flags for Android identity
MOBILE_FINGERPRINT_ARGS = [
    "--fingerprint-platform=android",
    "--fingerprint-gpu-vendor=Qualcomm",
    "--fingerprint-gpu-renderer=ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)",
    "--fingerprint-screen-width=412",
    "--fingerprint-screen-height=915",
    "--fingerprint-storage-quota=5000",
    "--fingerprint-hardware-concurrency=8",
    "--fingerprint-device-memory=8",
    # Disable Chromium's built-in ad blocker — we need ads to render
    "--disable-features=SubresourceFilter",
]

# Track temp user_data_dirs for cleanup.
# Maps context id -> user_data_dir path.
# Process-safe: each multiprocessing worker gets its own copy of this dict.
_CLOAKBROWSER_DIRS: Dict[int, str] = {}


async def configure_mobile_browser(
    config: dict,
    headless,
    proxy_cfg: Optional[Dict[str, str]],
    worker_id: int,
    get_random_delay_fn,
) -> Optional[dict]:
    """Configure and launch a mobile CloakBrowser session.

    Returns setup_result dict, or None on failure (caller handles fallback to desktop).
    """
    from cloakbrowser import launch_persistent_context_async

    emit_mobile_fingerprint_event(
        worker_id=worker_id,
        event_type="fingerprint_flow_started",
        strategy_mode="active",
        browser_family="chrome",
        os="android",
        final_mode="mobile",
    )

    # Build proxy URL string (CloakBrowser expects "http://user:pass@host:port")
    proxy_url = None
    if proxy_cfg and proxy_cfg.get("server"):
        proxy_url = build_full_proxy_url(proxy_cfg)

    # CloakBrowser uses headless=True/False (no "virtual" mode).
    # Servers run Xvfb, so headless=False is correct for headed-on-virtual-display.
    use_headless = True
    if headless is False:
        use_headless = False
    elif headless == "virtual":
        use_headless = False

    # Random fingerprint seed per session for unique identity
    seed = random.randint(10000, 99999)
    session_args = [f"--fingerprint={seed}"] + list(MOBILE_FINGERPRINT_ARGS)

    # Temp profile dir for persistent context (avoids incognito detection)
    user_data_dir = tempfile.mkdtemp(prefix="nexads_mobile_")

    try:
        launch_kwargs = {
            "headless": use_headless,
            "geoip": True,
            "viewport": MOBILE_VIEWPORT,
            "user_agent": MOBILE_UA,
            "is_mobile": True,
            "has_touch": True,
            "device_scale_factor": MOBILE_DPR,
            "args": session_args,
        }
        if proxy_url:
            launch_kwargs["proxy"] = proxy_url

        context = await launch_persistent_context_async(
            user_data_dir,
            **launch_kwargs,
        )

        _CLOAKBROWSER_DIRS[id(context)] = user_data_dir

        delay = get_random_delay_fn()
        await asyncio.sleep(delay)

        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type="mobile_context_ready",
            strategy_mode="active",
            final_mode="mobile",
            browser_family="chrome",
            os="android",
            reason=f"seed={seed}",
        )
        print(f"Worker {worker_id}: Mobile session activated with CloakBrowser (seed={seed})")

        return {
            "browser": None,
            "context": context,
            "context_options": {},
            "fingerprint_mode": "mobile",
            "fallback_reason": "",
            "validation_reason_codes": [],
            "is_persistent_context": True,
        }

    except Exception as e:
        print(f"Worker {worker_id}: CloakBrowser mobile launch failed: {e}")
        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type="fingerprint_fallback_triggered",
            strategy_mode="active",
            reason=str(e),
            fallback_target="desktop",
            final_mode="desktop",
        )
        # Clean up temp dir on failure
        try:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass
        return None


async def cleanup_mobile_context(context, worker_id: int):
    """Close CloakBrowser persistent context and delete temp profile dir."""
    user_data_dir = _CLOAKBROWSER_DIRS.pop(id(context), None)

    try:
        await asyncio.wait_for(context.close(), timeout=15)
    except asyncio.TimeoutError:
        print(f"Worker {worker_id}: CloakBrowser context close timed out")
    except Exception:
        pass

    if user_data_dir:
        try:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass
