"""
nexads/browser/setup.py
Browser initialization and cleanup.
Desktop: Camoufox (anti-detect Firefox).
Mobile: Patchright (undetected Chromium via persistent context).
"""

import random
import asyncio
import shutil
import tempfile
from typing import Optional, Dict, List
from urllib.parse import urlparse

from camoufox.async_api import AsyncCamoufox
from camoufox import DefaultAddons
from browserforge.fingerprints import Screen

from app.browser.mobile import (
    generate_mobile_fingerprint,
    get_fingerprint_summary,
)
from app.browser.geoip import get_geoip_data
from app.core.telemetry import emit_mobile_fingerprint_event


# Hardcoded mobile fingerprint strategy for this milestone.
MOBILE_FINGERPRINT_ADVANCED_OVERRIDE_ENABLED = False
MOBILE_FINGERPRINT_MAX_REGEN_ATTEMPTS = 1
MOBILE_FINGERPRINT_TIMEOUT_MS = 5000
MOBILE_HEADER_BROWSER = "chrome"
MOBILE_HEADER_OS = "android"

# Track patchright playwright instances and temp dirs for cleanup.
# Maps context id -> (pw_instance, user_data_dir)
_PATCHRIGHT_MANAGERS: Dict[int, tuple] = {}


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


def _header_get(headers_obj, key: str, default=""):
    """Read HTTP header value from dict-like header containers."""
    if headers_obj is None:
        return default
    if isinstance(headers_obj, dict):
        return headers_obj.get(key, default)
    if hasattr(headers_obj, "get"):
        value = headers_obj.get(key, default)
        return default if value is None else value
    return default


def _extract_target_domain_from_config(config: dict) -> str:
    """Extract first configured URL domain for fingerprint generation context."""
    urls = config.get("urls", [])
    if not isinstance(urls, list):
        return "example.com"

    for item in urls:
        if not isinstance(item, dict):
            continue
        raw_url = str(item.get("url", "")).strip()
        if not raw_url:
            continue

        # Handle comma-separated URLs used by random_page mode.
        candidate = raw_url.split(",")[0].strip()
        if not candidate:
            continue

        host = (urlparse(candidate).hostname or "").strip().lower()
        if host:
            return host

    return "example.com"


def _looks_like_host(value: str) -> bool:
    """Return True when value resembles a host or IP."""
    if not value:
        return False

    candidate = value.strip().lower()
    if candidate == "localhost":
        return True

    # Domain-like hosts usually include dots.
    if "." in candidate and " " not in candidate:
        return True

    # Basic IPv4 check.
    parts = candidate.split(".")
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return True

    return False


def _is_port(value: str) -> bool:
    """Return True when value is a valid TCP port string."""
    if not value or not value.isdigit():
        return False
    port_num = int(value)
    return 1 <= port_num <= 65535


def _parse_proxy_entry(proxy: str):
    """Parse proxy string to (host, port, username, password)."""
    value = (proxy or "").strip()
    if not value:
        return None

    username = None
    password = None
    host = None
    port = None

    if "@" in value:
        left, right = value.rsplit("@", 1)

        # Format: user:pass@host:port
        if ":" in right:
            candidate_host, candidate_port = right.rsplit(":", 1)
            if _is_port(candidate_port):
                host = candidate_host
                port = candidate_port
                if ":" in left:
                    username, password = left.split(":", 1)
                else:
                    username, password = left, ""
                return host, port, username, password

        # Format: host:port@user:pass
        if ":" in left and ":" in right:
            candidate_host, candidate_port = left.rsplit(":", 1)
            if _is_port(candidate_port):
                host = candidate_host
                port = candidate_port
                username, password = right.split(":", 1)
                return host, port, username, password

        return None

    # Formats without @.
    parts = value.split(":")

    # Format: host:port
    if len(parts) == 2 and _is_port(parts[1]):
        host, port = parts[0], parts[1]
        return host, port, None, None

    # Format: host:port:user:pass OR user:pass:host:port
    if len(parts) >= 4:
        # Prefer host-first when the first token looks like a host.
        if _is_port(parts[1]) and _looks_like_host(parts[0]):
            host = parts[0]
            port = parts[1]
            username = parts[2]
            password = ":".join(parts[3:])
            return host, port, username, password

        # Fallback to auth-first: user:pass:host:port
        if _is_port(parts[-1]):
            candidate_host = parts[-2]
            if _looks_like_host(candidate_host):
                host = candidate_host
                port = parts[-1]
                username = parts[0]
                password = ":".join(parts[1:-2])
                return host, port, username, password

    return None


def _resolve_proxy_config(config: dict) -> Optional[Dict[str, str]]:
    """Resolve and normalize one proxy config for browser launch."""
    proxy_value = None
    if config["proxy"]["credentials"]:
        proxy_value = config["proxy"]["credentials"]
    elif config["proxy"]["file"]:
        with open(config["proxy"]["file"], "r") as f:
            proxies = [line.strip() for line in f if line.strip()]
        if proxies:
            proxy_value = random.choice(proxies)

    if not proxy_value:
        return None

    proxy_type = config["proxy"]["type"].lower()
    parsed_proxy = _parse_proxy_entry(proxy_value)
    if not parsed_proxy:
        raise ValueError(
            "Unsupported proxy format. Use one of: "
            "ip:port, host:port:user:pass, host:port@user:pass, "
            "user:pass:host:port, user:pass@host:port"
        )

    host, port, user, pwd = parsed_proxy
    return {
        "server": f"{proxy_type}://{host}:{port}",
        "username": user,
        "password": pwd,
    }


async def _launch_mobile_patchright_context(
    headless_mode,
    proxy_cfg: Optional[Dict[str, str]],
    worker_id: int,
    context_options: Dict,
):
    """Launch Patchright persistent context for mobile sessions.

    Returns (context, pw_instance) — context is a BrowserContext with
    one default page already open.
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

    # Merge mobile context options from fingerprint + geoip.
    for key in (
        "viewport",
        "locale",
        "timezone_id",
        "device_scale_factor",
        "is_mobile",
        "has_touch",
        "extra_http_headers",
    ):
        if key in context_options:
            launch_kwargs[key] = context_options[key]

    if proxy_cfg:
        launch_kwargs["proxy"] = proxy_cfg
        # Prevent WebRTC from leaking real IP when using proxy.
        launch_kwargs["args"] = [
            "--webrtc-ip-handling-policy=disable_non_proxied_udp",
            "--enforce-webrtc-ip-permission-check",
        ]

    context = await pw.chromium.launch_persistent_context(**launch_kwargs)

    # Track pw instance and temp dir for cleanup.
    _PATCHRIGHT_MANAGERS[id(context)] = (pw, user_data_dir)

    return context, pw


def map_fingerprint_to_context_options(fingerprint: Optional[dict]) -> Dict:
    """Map BrowserForge fingerprint fields to Patchright persistent context options."""
    if not isinstance(fingerprint, dict):
        return {}

    navigator = fingerprint.get("navigator")
    screen = fingerprint.get("screen", {})

    context_opts = {}

    # Mobile identity flags.
    context_opts["is_mobile"] = True
    context_opts["has_touch"] = True

    # Viewport from fingerprint screen dimensions.
    width = _fp_get(screen, "width", 412)
    height = _fp_get(screen, "height", 915)
    if width and height:
        context_opts["viewport"] = {"width": int(width), "height": int(height)}

    dpr = _fp_get(screen, "devicePixelRatio")
    if dpr:
        context_opts["device_scale_factor"] = float(dpr)

    # Locale from navigator language.
    if lang := _fp_get(navigator, "language"):
        context_opts["locale"] = lang

    # DO NOT set user_agent — patchright works best with real Chrome UA.
    # DO NOT set custom browser headers — same reason.

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
                f"Platform mismatch: Android UA found with platform={platform} (expected Linux)"
            )
    elif "iPhone" in ua or "iPad" in ua:
        if platform and platform not in ["iPhone", "iPad"]:
            reason_codes.append("ua_platform_mismatch_ios")
            violations.append(
                f"Platform mismatch: iOS UA found with platform={platform} (expected iPhone/iPad)"
            )

    if "Android" in ua and "Mobile" not in ua:
        reason_codes.append("ua_android_without_mobile")
        violations.append(f"Impossible combo: Android UA without 'Mobile' keyword")

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

    is_valid = len(violations) == 0

    return is_valid, reason_codes, violations


async def configure_browser(config: dict, worker_id: int, get_random_delay_fn):
    """Configure and return browser setup result for one worker session."""
    try:
        proxy_cfg = _resolve_proxy_config(config)

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

        setup_result = {
            "browser": None,
            "context": None,
            "context_options": {},
            "fingerprint_mode": "desktop",
            "fallback_reason": "",
            "validation_reason_codes": [],
            "is_persistent_context": False,
        }

        # Desktop path: Camoufox only.
        if device_type != "mobile":
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

            setup_result["browser"] = await AsyncCamoufox(**options).start()
            delay = get_random_delay_fn()
            await asyncio.sleep(delay)
            return setup_result

        # Mobile path: Patchright persistent context + BrowserForge fingerprint.
        browser_family = MOBILE_HEADER_BROWSER
        mobile_os = MOBILE_HEADER_OS
        target_domain = _extract_target_domain_from_config(config)

        geoip_data = None
        proxy_server_url = proxy_cfg.get("server") if proxy_cfg else None
        if proxy_server_url:
            full_proxy_url = proxy_server_url
            if proxy_cfg.get("username") and proxy_cfg.get("password"):
                parsed = proxy_server_url.split("://")
                if len(parsed) == 2:
                    full_proxy_url = f"{parsed[0]}://{proxy_cfg['username']}:{proxy_cfg['password']}@{parsed[1]}"

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
                    print(
                        f"Worker {worker_id}: Geoip lookup failed, using fingerprint locale"
                    )
                    geoip_data = None
            except Exception as geo_err:
                print(
                    f"Worker {worker_id}: Geoip lookup failed ({str(geo_err)}), using fingerprint locale"
                )
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
                    fingerprint,
                    context_opts,
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
            setup_result["fallback_reason"] = (
                "|".join(reason_codes) if reason_codes else "preflight_failed"
            )
            setup_result["validation_reason_codes"] = reason_codes
            emit_mobile_fingerprint_event(
                worker_id=worker_id,
                event_type="fingerprint_fallback_triggered",
                strategy_mode="active",
                reason_codes=reason_codes,
                reason=setup_result["fallback_reason"],
                fallback_target="desktop",
                final_mode="desktop",
            )
            # Fallback to desktop engine when mobile fingerprint preflight cannot pass.
            os_fingerprint = random.choice(config["os_fingerprint"])
            fallback_options = {
                "headless": headless,
                "os": os_fingerprint,
                "screen": Screen(max_width=1920, max_height=1080),
                "geoip": True,
                "humanize": True,
            }
            if config["browser"]["disable_ublock"]:
                fallback_options["exclude_addons"] = [DefaultAddons.UBO]
            if proxy_cfg:
                fallback_options["proxy"] = proxy_cfg

            setup_result["browser"] = await AsyncCamoufox(**fallback_options).start()
            delay = get_random_delay_fn()
            await asyncio.sleep(delay)
            print(
                f"Worker {worker_id}: Mobile fingerprint preflight failed, continuing desktop flow"
            )
            return setup_result

        fp_summary = get_fingerprint_summary(fingerprint)

        # Apply geoip overrides to context options.
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
        context, pw = await _launch_mobile_patchright_context(
            headless_mode=headless,
            proxy_cfg=proxy_cfg,
            worker_id=worker_id,
            context_options=context_opts,
        )
        delay = get_random_delay_fn()
        await asyncio.sleep(delay)

        setup_result["context"] = context
        setup_result["context_options"] = context_opts
        setup_result["fingerprint_mode"] = "mobile"
        setup_result["geoip_data"] = geoip_data
        setup_result["is_persistent_context"] = True

        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type="mobile_context_ready",
            strategy_mode="active",
            final_mode="mobile",
            browser_family=browser_family,
            os=mobile_os,
            **fp_summary,
        )
        print(
            f"Worker {worker_id}: Mobile session activated with patchright (channel=chrome)"
        )
        return setup_result

    except Exception as e:
        print(f"Worker {worker_id}: Browser initialization error: {str(e)}")
        return None


async def cleanup_browser(browser, worker_id: int, context=None):
    """Clean up browser contexts and close the browser.

    For desktop (Camoufox): closes contexts then browser.
    For mobile (Patchright): closes persistent context then stops playwright.
    """
    try:
        # Patchright persistent context path.
        if context is not None:
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
            # Delete temp profile directory.
            if user_data_dir:
                try:
                    shutil.rmtree(user_data_dir, ignore_errors=True)
                except Exception:
                    pass
            return

        # Camoufox desktop path.
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

    except Exception as e:
        print(f"Worker {worker_id}: Error during browser cleanup: {str(e)}")
