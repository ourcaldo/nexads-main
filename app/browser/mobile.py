"""
app/browser/mobile.py
Mobile browser sessions using Patchright (undetected Chromium)
with BrowserForge fingerprint generation.
"""

import asyncio
import random
import shutil
import tempfile
from typing import Optional, Dict, Tuple, List

from browserforge.fingerprints import FingerprintGenerator

from app.browser.geoip import get_geoip_data
from app.browser.proxy import build_full_proxy_url
from app.core.telemetry import emit_mobile_fingerprint_event


# Hardcoded mobile fingerprint strategy for this milestone.
MOBILE_FINGERPRINT_MAX_REGEN_ATTEMPTS = 1
MOBILE_FINGERPRINT_TIMEOUT_MS = 5000
MOBILE_HEADER_BROWSER = "chrome"
MOBILE_HEADER_OS = "android"

# Track patchright playwright instances and temp dirs for cleanup.
# Maps context id -> (pw_instance, user_data_dir)
_PATCHRIGHT_MANAGERS: Dict[int, tuple] = {}


# ---------------------------------------------------------------------------
# Fingerprint field helpers
# ---------------------------------------------------------------------------

def _fp_get(obj, key: str, default=None):
    """Read fingerprint fields from either dict-like or typed objects."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        value = obj.get(key, default)
        return default if value is None else value
    if hasattr(obj, key):
        value = getattr(obj, key)
        return default if value is None else value

    aliases = {
        "userAgent": "user_agent",
        "maxTouchPoints": "max_touch_points",
        "devicePixelRatio": "device_pixel_ratio",
    }
    alias = aliases.get(key)
    if alias and hasattr(obj, alias):
        value = getattr(obj, alias)
        return default if value is None else value

    return default


# ---------------------------------------------------------------------------
# Fingerprint generation
# ---------------------------------------------------------------------------

async def generate_mobile_fingerprint(
    domain: str,
    browser_family: str,
    os: str,
    screen_constraints: dict,
    worker_id: int,
    max_retries: int = 1,
    timeout_ms: int = 5000,
    retry_count: int = 0,
) -> Optional[dict]:
    """Generate a full BrowserForge mobile fingerprint payload."""
    try:
        retry_policy = "regenerate_once"

        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type="profile_generation_started",
            browser_family=browser_family,
            os=os,
        )

        generator = FingerprintGenerator()

        import time
        start_time = time.time()
        fp_obj = await asyncio.wait_for(
            asyncio.to_thread(
                generator.generate,
                browser=browser_family,
                os=os,
                device="mobile",
            ),
            timeout=timeout_ms / 1000.0,
        )
        generation_ms = int((time.time() - start_time) * 1000)

        def _to_plain(obj):
            if obj is None:
                return None
            if isinstance(obj, (str, int, float, bool)):
                return obj
            if isinstance(obj, dict):
                return {str(k): _to_plain(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple, set)):
                return [_to_plain(v) for v in obj]
            if hasattr(obj, "model_dump"):
                try:
                    return _to_plain(obj.model_dump())
                except Exception:
                    pass
            if hasattr(obj, "__dict__"):
                return {
                    str(k): _to_plain(v)
                    for k, v in vars(obj).items()
                    if not str(k).startswith("_")
                }
            return str(obj)

        mobile_identity = _to_plain(fp_obj)
        if not isinstance(mobile_identity, dict):
            raise ValueError("BrowserForge fingerprint conversion failed")

        headers = mobile_identity.get("headers", {})
        if isinstance(headers, dict):
            mobile_identity["headers"] = {
                str(k): str(v)
                for k, v in headers.items()
                if k is not None and v is not None
            }

        navigator = mobile_identity.get("navigator", {})
        ua_snippet = str(_fp_get(navigator, "userAgent", "N/A"))[:60]
        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type="profile_generated",
            browser_family=browser_family,
            os=os,
            ua_snippet=ua_snippet,
            platform=_fp_get(navigator, "platform", "N/A"),
            locale=_fp_get(navigator, "language", "en-US"),
            generation_ms=generation_ms,
        )

        print(
            f"Worker {worker_id}: Mobile fingerprint generated ({browser_family}/{os}, "
            f"ua_snippet={ua_snippet}...)"
        )
        return mobile_identity

    except asyncio.TimeoutError:
        print(
            f"Worker {worker_id}: Fingerprint generation timeout after {timeout_ms}ms "
            f"(attempt {retry_count + 1})"
        )
        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type="profile_generation_started",
            browser_family=browser_family,
            os=os,
            reason=f"Timeout after {timeout_ms}ms",
        )
        if retry_count < max_retries:
            await asyncio.sleep(random.uniform(0.5, 1.0))
            return await generate_mobile_fingerprint(
                domain, browser_family, os, screen_constraints, worker_id,
                max_retries=max_retries, timeout_ms=timeout_ms,
                retry_count=retry_count + 1,
            )
        return None

    except Exception as e:
        print(
            f"Worker {worker_id}: Fingerprint generation error: {str(e)} "
            f"(attempt {retry_count + 1})"
        )
        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type="profile_generation_started",
            browser_family=browser_family,
            os=os,
            reason=f"Error: {str(e)}",
        )
        if retry_count < max_retries:
            await asyncio.sleep(random.uniform(0.5, 1.0))
            return await generate_mobile_fingerprint(
                domain, browser_family, os, screen_constraints, worker_id,
                max_retries=max_retries, timeout_ms=timeout_ms,
                retry_count=retry_count + 1,
            )
        return None


def get_fingerprint_summary(fingerprint: Optional[dict]) -> dict:
    """Extract summary fields from a BrowserForge fingerprint for telemetry."""
    if not fingerprint:
        return {}

    navigator = fingerprint.get("navigator") if isinstance(fingerprint, dict) else None
    headers = fingerprint.get("headers") if isinstance(fingerprint, dict) else None

    ua = str(_fp_get(navigator, "userAgent", "N/A"))
    ua_snippet = ua[:60] if ua else "N/A"

    if isinstance(headers, dict):
        sec_ch_ua_mobile = headers.get("Sec-CH-UA-Mobile", "N/A")
    elif hasattr(headers, "get"):
        sec_ch_ua_mobile = headers.get("Sec-CH-UA-Mobile", "N/A")
    else:
        sec_ch_ua_mobile = "N/A"

    return {
        "ua_snippet": ua_snippet,
        "platform": _fp_get(navigator, "platform", "N/A"),
        "locale": _fp_get(navigator, "language", "en"),
        "max_touch_points": _fp_get(navigator, "maxTouchPoints", 0),
        "sec_ch_ua_mobile": sec_ch_ua_mobile,
    }


# ---------------------------------------------------------------------------
# Fingerprint → context options mapping & validation
# ---------------------------------------------------------------------------

def map_fingerprint_to_context_options(fingerprint: Optional[dict]) -> Dict:
    """Map BrowserForge fingerprint fields to Patchright persistent context options."""
    if not isinstance(fingerprint, dict):
        return {}

    navigator = fingerprint.get("navigator")
    screen = fingerprint.get("screen", {})

    context_opts = {}
    context_opts["is_mobile"] = True
    context_opts["has_touch"] = True

    width = _fp_get(screen, "width", 412)
    height = _fp_get(screen, "height", 915)
    if width and height:
        context_opts["viewport"] = {"width": int(width), "height": int(height)}

    dpr = _fp_get(screen, "devicePixelRatio")
    if dpr:
        context_opts["device_scale_factor"] = float(dpr)

    if lang := _fp_get(navigator, "language"):
        context_opts["locale"] = lang

    return context_opts


def validate_fingerprint_consistency(
    fingerprint: Optional[dict], context_opts: Dict
) -> tuple[bool, List[str], List[str]]:
    """Validate consistency of mobile fingerprint identity."""
    reason_codes = []
    violations = []

    if not fingerprint:
        return False, ["fingerprint_missing"], ["Fingerprint is missing"]

    navigator = fingerprint.get("navigator") if isinstance(fingerprint, dict) else None
    ua = str(_fp_get(navigator, "userAgent", ""))
    platform = str(_fp_get(navigator, "platform", ""))

    has_mobile_in_ua = "Mobile" in ua
    is_mobile_flag = context_opts.get("is_mobile", False)
    if has_mobile_in_ua and not is_mobile_flag:
        reason_codes.append("mobile_flag_mismatch")
        violations.append("Mobile flag mismatch: UA has 'Mobile' but is_mobile=False")
    if not has_mobile_in_ua and is_mobile_flag:
        reason_codes.append("mobile_keyword_missing")
        violations.append("UA missing 'Mobile' while is_mobile=True")

    max_touch = int(_fp_get(navigator, "maxTouchPoints", 0))
    has_touch_flag = context_opts.get("has_touch", False)
    if max_touch > 0 and not has_touch_flag:
        reason_codes.append("touch_flag_mismatch")
        violations.append(
            f"Touch flag mismatch: maxTouchPoints={max_touch} but has_touch=False"
        )

    if "Android" in ua:
        if platform and not platform.startswith("Linux"):
            reason_codes.append("ua_platform_mismatch_android")
            violations.append(
                f"Platform mismatch: Android UA found with platform={platform}"
            )
    elif "iPhone" in ua or "iPad" in ua:
        if platform and platform not in ["iPhone", "iPad"]:
            reason_codes.append("ua_platform_mismatch_ios")
            violations.append(
                f"Platform mismatch: iOS UA found with platform={platform}"
            )

    if "Android" in ua and "Mobile" not in ua:
        reason_codes.append("ua_android_without_mobile")
        violations.append("Impossible combo: Android UA without 'Mobile' keyword")

    if max_touch < 5 and ("iPhone" in ua or "iPad" in ua):
        reason_codes.append("ua_ios_low_touchpoints")
        violations.append(
            f"Impossible combo: iOS UA with maxTouchPoints={max_touch} (expected >=5)"
        )

    locale = str(context_opts.get("locale", "") or "")
    headers = context_opts.get("extra_http_headers", {})
    accept_language = str((headers or {}).get("Accept-Language", "") or "")
    if (
        locale
        and accept_language
        and not accept_language.lower().startswith(locale.lower().split("-")[0])
    ):
        reason_codes.append("locale_header_mismatch")
        violations.append(
            f"Locale/header mismatch: locale={locale}, Accept-Language={accept_language}"
        )

    return len(violations) == 0, reason_codes, violations


# ---------------------------------------------------------------------------
# Patchright launch & cleanup
# ---------------------------------------------------------------------------

async def launch_mobile_context(
    headless_mode,
    proxy_cfg: Optional[Dict[str, str]],
    worker_id: int,
    context_options: Dict,
):
    """Launch Patchright persistent context for mobile sessions.

    Returns (context, pw_instance).
    """
    from patchright.async_api import async_playwright

    pw = await async_playwright().start()

    user_data_dir = tempfile.mkdtemp(prefix="nexads_mobile_")

    launch_kwargs = {
        "user_data_dir": user_data_dir,
        "channel": "chrome",
        "headless": False if headless_mode is False else True,
        "no_viewport": False,
    }

    for key in (
        "viewport", "locale", "timezone_id", "device_scale_factor",
        "is_mobile", "has_touch", "extra_http_headers",
    ):
        if key in context_options:
            launch_kwargs[key] = context_options[key]

    if proxy_cfg:
        launch_kwargs["proxy"] = proxy_cfg
        launch_kwargs["args"] = [
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--enforce-webrtc-ip-permission-check",
            "--dns-over-https-templates=https://cloudflare-dns.com/dns-query",
            "--dns-over-https-mode=secure",
        ]

    context = await pw.chromium.launch_persistent_context(**launch_kwargs)

    _PATCHRIGHT_MANAGERS[id(context)] = (pw, user_data_dir)

    return context, pw


async def cleanup_mobile_context(context, worker_id: int):
    """Close Patchright persistent context, stop playwright, delete temp dir."""
    manager_data = _PATCHRIGHT_MANAGERS.pop(id(context), None)
    pw = None
    user_data_dir = None
    if isinstance(manager_data, tuple):
        pw = manager_data[0]
        user_data_dir = manager_data[1] if len(manager_data) > 1 else None

    try:
        await context.close()
    except Exception:
        pass
    if pw:
        try:
            await pw.stop()
        except Exception:
            pass
    if user_data_dir:
        try:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass


async def configure_mobile_browser(
    config: dict,
    headless,
    proxy_cfg: Optional[Dict[str, str]],
    worker_id: int,
    get_random_delay_fn,
) -> dict:
    """Configure and launch a mobile Patchright session.

    Returns setup_result dict. Falls back to None on failure (caller handles fallback).
    """
    from urllib.parse import urlparse

    browser_family = MOBILE_HEADER_BROWSER
    mobile_os = MOBILE_HEADER_OS

    # Extract target domain for fingerprint context.
    target_domain = "example.com"
    urls = config.get("urls", [])
    if isinstance(urls, list):
        for item in urls:
            if not isinstance(item, dict):
                continue
            raw_url = str(item.get("url", "")).strip().split(",")[0].strip()
            host = (urlparse(raw_url).hostname or "").strip().lower()
            if host:
                target_domain = host
                break

    # GeoIP lookup via proxy.
    geoip_data = None
    if proxy_cfg and proxy_cfg.get("server"):
        full_proxy_url = build_full_proxy_url(proxy_cfg)
        print(f"Worker {worker_id}: Attempting geoip lookup via proxy...")
        try:
            geoip_data = await get_geoip_data(full_proxy_url)
            if geoip_data and geoip_data.get("country_code"):
                print(
                    f"Worker {worker_id}: Geoip data: "
                    f"country={geoip_data.get('country_code')}, "
                    f"timezone={geoip_data.get('timezone')}, "
                    f"locale={geoip_data.get('locale')}"
                )
                emit_mobile_fingerprint_event(
                    worker_id=worker_id,
                    event_type="geoip_lookup",
                    strategy_mode="active",
                    country=geoip_data.get("country_code"),
                    timezone=geoip_data.get("timezone"),
                    locale=geoip_data.get("locale"),
                )
            else:
                print(f"Worker {worker_id}: Geoip lookup failed, using fingerprint locale")
                geoip_data = None
        except Exception as geo_err:
            print(f"Worker {worker_id}: Geoip lookup failed ({geo_err}), using fingerprint locale")
            geoip_data = None
    else:
        print(f"Worker {worker_id}: No proxy configured, using fingerprint locale")

    emit_mobile_fingerprint_event(
        worker_id=worker_id,
        event_type="fingerprint_flow_started",
        strategy_mode="active",
        browser_family=browser_family,
        os=mobile_os,
        final_mode="mobile",
    )

    # Generate and validate fingerprint.
    fingerprint = None
    context_opts = {}
    reason_codes: List[str] = []
    violations: List[str] = []

    for attempt in range(MOBILE_FINGERPRINT_MAX_REGEN_ATTEMPTS + 1):
        fingerprint = await generate_mobile_fingerprint(
            domain=target_domain,
            browser_family=browser_family,
            os=mobile_os,
            screen_constraints={},
            worker_id=worker_id,
            max_retries=0,
            timeout_ms=MOBILE_FINGERPRINT_TIMEOUT_MS,
        )

        if not fingerprint:
            reason_codes = ["generation_failed"]
            violations = ["Fingerprint generation returned no value"]
        else:
            context_opts = map_fingerprint_to_context_options(fingerprint)
            is_valid, reason_codes, violations = validate_fingerprint_consistency(
                fingerprint, context_opts,
            )
            emit_mobile_fingerprint_event(
                worker_id=worker_id,
                event_type="fingerprint_validation_result",
                strategy_mode="active",
                is_valid=is_valid,
                violation_count=len(violations),
                violations=violations,
                reason_codes=reason_codes,
                reason="|".join(reason_codes) if reason_codes else "ok",
            )
            if is_valid:
                break

        if attempt >= MOBILE_FINGERPRINT_MAX_REGEN_ATTEMPTS:
            fingerprint = None
            break

        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type="fingerprint_regeneration",
            strategy_mode="active",
            reason_codes=reason_codes,
            reason="|".join(reason_codes) if reason_codes else "generation_failed",
            fallback_target="regenerate",
        )

    if not fingerprint:
        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type="fingerprint_fallback_triggered",
            strategy_mode="active",
            reason_codes=reason_codes,
            reason="|".join(reason_codes) if reason_codes else "preflight_failed",
            fallback_target="desktop",
            final_mode="desktop",
        )
        print(f"Worker {worker_id}: Mobile fingerprint preflight failed")
        return None

    fp_summary = get_fingerprint_summary(fingerprint)

    # Apply geoip overrides.
    if geoip_data:
        if geoip_data.get("locale"):
            context_opts["locale"] = geoip_data["locale"]
        if geoip_data.get("timezone"):
            context_opts["timezone_id"] = geoip_data["timezone"]
        accept_lang = geoip_data.get("locale", "en-US")
        context_opts.setdefault("extra_http_headers", {})
        context_opts["extra_http_headers"]["Accept-Language"] = accept_lang
    else:
        print(
            f"Worker {worker_id}: WARNING - No geoip data available. "
            f"Timezone will not match proxy IP (detection risk)."
        )

    # Launch patchright persistent context.
    context, pw = await launch_mobile_context(
        headless_mode=headless,
        proxy_cfg=proxy_cfg,
        worker_id=worker_id,
        context_options=context_opts,
    )
    delay = get_random_delay_fn()
    await asyncio.sleep(delay)

    emit_mobile_fingerprint_event(
        worker_id=worker_id,
        event_type="mobile_context_ready",
        strategy_mode="active",
        final_mode="mobile",
        browser_family=browser_family,
        os=mobile_os,
        **fp_summary,
    )
    print(f"Worker {worker_id}: Mobile session activated with patchright (channel=chrome)")

    return {
        "browser": None,
        "context": context,
        "context_options": context_opts,
        "fingerprint_mode": "mobile",
        "fallback_reason": "",
        "validation_reason_codes": [],
        "is_persistent_context": True,
        "geoip_data": geoip_data,
    }


# ---------------------------------------------------------------------------
# Kept for backward compatibility (unused helpers)
# ---------------------------------------------------------------------------

def parse_mobile_constraints(hardcoded_bounds: dict | None = None) -> dict:
    """Extract and validate mobile constraint bounds."""
    screen = hardcoded_bounds or {}
    return {
        "min_width": max(360, screen.get("min_width", 360)),
        "max_width": min(430, screen.get("max_width", 430)),
        "min_height": max(740, screen.get("min_height", 740)),
        "max_height": min(932, screen.get("max_height", 932)),
    }


def select_mobile_fingerprint_params(
    browsers: List[str] | None = None,
    os_list: List[str] | None = None,
) -> Tuple[str, str]:
    """Select random browser family and OS for mobile fingerprint."""
    browsers = browsers or ["chrome", "safari"]
    os_list = os_list or ["android", "ios"]

    candidate_pairs = [("chrome", "android"), ("safari", "ios")]
    valid_pairs = [
        pair for pair in candidate_pairs
        if pair[0] in browsers and pair[1] in os_list
    ]

    if valid_pairs:
        return random.choice(valid_pairs)
    return "chrome", "android"
