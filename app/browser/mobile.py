"""
app/browser/mobile.py
Mobile browser sessions using CloakBrowser (stealth Chromium with source-level patches)
and BrowserForge for random Android fingerprint generation.
"""

import asyncio
import random
import shutil
import tempfile
from typing import Optional, Dict

from browserforge.fingerprints import FingerprintGenerator

from app.browser.proxy import build_full_proxy_url
from app.core.telemetry import emit_mobile_fingerprint_event
from app.core.timings import timing_seconds

# Track temp user_data_dirs for cleanup.
# Maps context id -> user_data_dir path.
# Process-safe: each multiprocessing worker gets its own copy of this dict.
_CLOAKBROWSER_DIRS: Dict[int, str] = {}

# Shared fingerprint generator (one per process)
_FP_GENERATOR: FingerprintGenerator | None = None


def _get_generator() -> FingerprintGenerator:
    """Lazy-init fingerprint generator once per process."""
    global _FP_GENERATOR
    if _FP_GENERATOR is None:
        _FP_GENERATOR = FingerprintGenerator()
    return _FP_GENERATOR


def _generate_mobile_profile(worker_id: int) -> dict:
    """Generate a random Android mobile profile via BrowserForge.

    Returns dict with all fields needed for CloakBrowser launch.
    """
    fp = _get_generator().generate(browser="chrome", os="android", device="mobile")

    nav = fp.navigator
    screen = fp.screen
    vc = fp.videoCard

    ua = nav.userAgent or ""
    gpu_vendor = vc.vendor or "Qualcomm"
    gpu_renderer = vc.renderer or "ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)"
    width = int(screen.width or 412)
    height = int(screen.height or 915)
    dpr = float(screen.devicePixelRatio or 2.625)
    hw_concurrency = int(nav.hardwareConcurrency or 8)
    device_memory = int(nav.deviceMemory or 8)

    # Ensure reasonable screen dimensions
    width = max(320, min(480, width))
    height = max(640, min(960, height))

    profile = {
        "user_agent": ua,
        "viewport": {"width": width, "height": height},
        "device_scale_factor": dpr,
        "gpu_vendor": gpu_vendor,
        "gpu_renderer": gpu_renderer,
        "screen_width": width,
        "screen_height": height,
        "hw_concurrency": hw_concurrency,
        "device_memory": device_memory,
    }

    print(
        f"Worker {worker_id}: BrowserForge mobile profile — "
        f"screen={width}x{height}@{dpr}x, gpu={gpu_renderer[:50]}..., "
        f"ua={ua[:60]}..."
    )
    return profile


async def configure_mobile_browser(
    config: dict,
    headless,
    proxy_cfg: Optional[Dict[str, str]],
    worker_id: int,
    get_random_delay_fn,
) -> Optional[dict]:
    """Configure and launch a mobile CloakBrowser session.

    Uses BrowserForge to generate a random Android fingerprint, then passes
    the fields as CloakBrowser binary flags for source-level enforcement.

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

    # Generate random Android fingerprint
    profile = _generate_mobile_profile(worker_id)

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

    # Random fingerprint seed per session for canvas/audio/font noise
    seed = random.randint(10000, 99999)
    session_args = [
        f"--fingerprint={seed}",
        "--fingerprint-platform=android",
        f"--fingerprint-gpu-vendor={profile['gpu_vendor']}",
        f"--fingerprint-gpu-renderer={profile['gpu_renderer']}",
        f"--fingerprint-screen-width={profile['screen_width']}",
        f"--fingerprint-screen-height={profile['screen_height']}",
        f"--fingerprint-hardware-concurrency={profile['hw_concurrency']}",
        f"--fingerprint-device-memory={profile['device_memory']}",
        "--fingerprint-storage-quota=5000",
        "--disable-features=SubresourceFilter,AdsInterventions,HeavyAdIntervention,HeavyAdPrivacyMitigations",
    ]

    # Temp profile dir for persistent context (avoids incognito detection)
    user_data_dir = tempfile.mkdtemp(prefix="nexads_mobile_")

    try:
        launch_kwargs = {
            "headless": use_headless,
            "geoip": True,
            "viewport": profile["viewport"],
            "user_agent": profile["user_agent"],
            "is_mobile": True,
            "has_touch": True,
            "device_scale_factor": profile["device_scale_factor"],
            "args": session_args,
        }
        if proxy_url:
            launch_kwargs["proxy"] = proxy_url

        context = await asyncio.wait_for(
            launch_persistent_context_async(user_data_dir, **launch_kwargs),
            timeout=90,
        )

        _CLOAKBROWSER_DIRS[id(context)] = user_data_dir

        await asyncio.sleep(timing_seconds("page_settle"))

        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type="mobile_context_ready",
            strategy_mode="active",
            final_mode="mobile",
            browser_family="chrome",
            os="android",
            ua_snippet=profile["user_agent"][:60],
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
