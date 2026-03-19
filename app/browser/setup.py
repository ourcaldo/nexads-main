"""
nexads/browser/setup.py
Browser initialization and cleanup using Camoufox.
"""

import random
import asyncio
from typing import Optional, Dict, List

from camoufox.async_api import AsyncCamoufox
from camoufox import DefaultAddons
from browserforge.fingerprints import Screen, Fingerprint

from app.browser.mobile import (
    generate_mobile_fingerprint,
    get_fingerprint_summary,
    parse_mobile_constraints,
    select_mobile_fingerprint_params
)
from app.core.telemetry import emit_mobile_fingerprint_event


# Hardcoded mobile fingerprint strategy for this milestone.
MOBILE_FINGERPRINT_ENABLED = False
MOBILE_FINGERPRINT_DRY_RUN = True
MOBILE_FINGERPRINT_MAX_REGEN_ATTEMPTS = 1
MOBILE_FINGERPRINT_TIMEOUT_MS = 5000
MOBILE_FINGERPRINT_BROWSERS = ["chrome", "safari"]
MOBILE_FINGERPRINT_OSES = ["android", "ios"]
MOBILE_SCREEN_BOUNDS = {
    "min_width": 360,
    "max_width": 430,
    "min_height": 740,
    "max_height": 932,
}
MOBILE_TARGET_DOMAIN = "example.com"


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


def map_fingerprint_to_context_options(fingerprint: Optional[Fingerprint]) -> Dict:
    """
    Map BrowserForge fingerprint fields to Playwright context options (Task 3).
    
    Args:
        fingerprint: BrowserForge Fingerprint object or None
    
    Returns:
        Dict of context_options for browser.new_context(**options)
    """
    if not fingerprint:
        return {}
    
    navigator = fingerprint.navigator or {}
    screen = fingerprint.screen or {}
    headers = fingerprint.headers or {}
    
    context_opts = {}
    
    if ua := navigator.get('userAgent'):
        context_opts['user_agent'] = ua
    
    width = screen.get('width', 360)
    height = screen.get('height', 740)
    context_opts['viewport'] = {'width': width, 'height': height}
    
    if dpr := screen.get('devicePixelRatio'):
        context_opts['device_scale_factor'] = float(dpr)
    
    context_opts['is_mobile'] = True
    max_touch = navigator.get('maxTouchPoints', 5)
    context_opts['has_touch'] = max_touch > 0
    
    if lang := navigator.get('language'):
        context_opts['locale'] = lang
    
    safe_headers = {}
    if headers:
        header_keys = [
            'User-Agent', 'Accept-Language', 'Accept', 'Accept-Encoding',
            'Sec-Fetch-Site', 'Sec-Fetch-Mode', 'Sec-Fetch-Dest',
            'Sec-CH-UA', 'Sec-CH-UA-Mobile', 'Sec-CH-UA-Platform',
            'Upgrade-Insecure-Requests'
        ]
        for key in header_keys:
            if key in headers and headers[key]:
                safe_headers[key] = str(headers[key])
        
    locale = context_opts.get('locale', '')
    if locale and 'Accept-Language' not in safe_headers:
        safe_headers['Accept-Language'] = locale

    if safe_headers:
        context_opts['extra_http_headers'] = safe_headers
    
    return context_opts


def validate_fingerprint_consistency(
    fingerprint: Optional[Fingerprint],
    context_opts: Dict
) -> tuple[bool, List[str], List[str]]:
    """
    Validate consistency of mobile fingerprint identity (Task 4).
    
    Args:
        fingerprint: BrowserForge Fingerprint object or None
        context_opts: Mapped context options
    
    Returns:
        Tuple of (is_valid, reason_codes, violations)
    """
    reason_codes = []
    violations = []
    
    if not fingerprint:
        return False, ['fingerprint_missing'], ['Fingerprint is missing']
    
    navigator = fingerprint.navigator or {}
    ua = navigator.get('userAgent', '')
    platform = navigator.get('platform', '')
    
    has_mobile_in_ua = 'Mobile' in ua
    is_mobile_flag = context_opts.get('is_mobile', False)
    if has_mobile_in_ua and not is_mobile_flag:
        reason_codes.append('mobile_flag_mismatch')
        violations.append("Mobile flag mismatch: UA has 'Mobile' but is_mobile=False")
    if not has_mobile_in_ua and is_mobile_flag:
        reason_codes.append('mobile_keyword_missing')
        violations.append("UA missing 'Mobile' while is_mobile=True")
    
    max_touch = navigator.get('maxTouchPoints', 0)
    has_touch_flag = context_opts.get('has_touch', False)
    if max_touch > 0 and not has_touch_flag:
        reason_codes.append('touch_flag_mismatch')
        violations.append(f"Touch flag mismatch: maxTouchPoints={max_touch} but has_touch=False")
    
    if 'Android' in ua:
        if platform and not platform.startswith('Linux'):
            reason_codes.append('ua_platform_mismatch_android')
            violations.append(f"Platform mismatch: Android UA found with platform={platform} (expected Linux)")
    elif 'iPhone' in ua or 'iPad' in ua:
        if platform and platform not in ['iPhone', 'iPad']:
            reason_codes.append('ua_platform_mismatch_ios')
            violations.append(f"Platform mismatch: iOS UA found with platform={platform} (expected iPhone/iPad)")
    
    if 'Android' in ua and 'Mobile' not in ua:
        reason_codes.append('ua_android_without_mobile')
        violations.append(f"Impossible combo: Android UA without 'Mobile' keyword")
    
    if max_touch < 5 and ('iPhone' in ua or 'iPad' in ua):
        reason_codes.append('ua_ios_low_touchpoints')
        violations.append(f"Impossible combo: iOS UA with maxTouchPoints={max_touch} (expected ≥5)")

    locale = str(context_opts.get('locale', '') or '')
    headers = context_opts.get('extra_http_headers', {})
    accept_language = str((headers or {}).get('Accept-Language', '') or '')
    if locale and accept_language and not accept_language.lower().startswith(locale.lower().split('-')[0]):
        reason_codes.append('locale_header_mismatch')
        violations.append(f"Locale/header mismatch: locale={locale}, Accept-Language={accept_language}")

    viewport = context_opts.get('viewport', {})
    width = int(viewport.get('width', 0)) if isinstance(viewport, dict) else 0
    height = int(viewport.get('height', 0)) if isinstance(viewport, dict) else 0
    if width < MOBILE_SCREEN_BOUNDS['min_width'] or width > MOBILE_SCREEN_BOUNDS['max_width']:
        reason_codes.append('viewport_width_out_of_bounds')
        violations.append(f"Viewport width {width} outside mobile bounds")
    if height < MOBILE_SCREEN_BOUNDS['min_height'] or height > MOBILE_SCREEN_BOUNDS['max_height']:
        reason_codes.append('viewport_height_out_of_bounds')
        violations.append(f"Viewport height {height} outside mobile bounds")
    
    is_valid = len(violations) == 0
    
    return is_valid, reason_codes, violations


async def configure_browser(config: dict, worker_id: int, get_random_delay_fn):
    """Configure and return browser setup result for one worker session."""
    try:
        proxy = None
        if config['proxy']['credentials']:
            proxy = config['proxy']['credentials']
        elif config['proxy']['file']:
            with open(config['proxy']['file'], 'r') as f:
                proxies = [line.strip() for line in f if line.strip()]
            if proxies:
                proxy = random.choice(proxies)

        headless = True
        if config['browser']['headless_mode'] == 'False':
            headless = False
        elif config['browser']['headless_mode'] == 'virtual':
            headless = 'virtual'

        os_fingerprint = random.choice(config['os_fingerprint'])

        device_type = random.choices(
            ['mobile', 'desktop'],
            weights=[
                config['device_type']['mobile'],
                config['device_type']['desktop']
            ],
            k=1
        )[0]

        # Mobile screens are smaller than desktop — cap accordingly
        screen = Screen(max_width=430, max_height=932) if device_type == 'mobile' \
                else Screen(max_width=1920, max_height=1080)

        options = {
            'headless': headless,
            'os': os_fingerprint,
            'screen': screen,
            'geoip': True,
            'humanize': True
        }

        if config['browser']['disable_ublock']:
            options['exclude_addons'] = [DefaultAddons.UBO]

        if proxy:
            proxy_type = config['proxy']['type'].lower()
            parsed_proxy = _parse_proxy_entry(proxy)
            if not parsed_proxy:
                raise ValueError(
                    "Unsupported proxy format. Use one of: "
                    "ip:port, host:port:user:pass, host:port@user:pass, "
                    "user:pass:host:port, user:pass@host:port"
                )

            host, port, user, pwd = parsed_proxy
            options['proxy'] = {
                'server': f"{proxy_type}://{host}:{port}",
                'username': user,
                'password': pwd
            }

        browser = await AsyncCamoufox(**options).start()
        delay = get_random_delay_fn()
        await asyncio.sleep(delay)

        setup_result = {
            'browser': browser,
            'context_options': {},
            'fingerprint_mode': 'desktop',
            'fallback_reason': '',
            'validation_reason_codes': [],
        }

        if not MOBILE_FINGERPRINT_ENABLED:
            return setup_result

        constraints = parse_mobile_constraints(MOBILE_SCREEN_BOUNDS)
        browser_family, mobile_os = select_mobile_fingerprint_params(
            MOBILE_FINGERPRINT_BROWSERS,
            MOBILE_FINGERPRINT_OSES,
        )

        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type='fingerprint_flow_started',
            browser_family=browser_family,
            os=mobile_os,
            final_mode='dry_run' if MOBILE_FINGERPRINT_DRY_RUN else 'mobile',
        )

        fingerprint = None
        context_opts = {}
        reason_codes: List[str] = []
        violations: List[str] = []

        for attempt in range(MOBILE_FINGERPRINT_MAX_REGEN_ATTEMPTS + 1):
            fingerprint = await generate_mobile_fingerprint(
                domain=MOBILE_TARGET_DOMAIN,
                browser_family=browser_family,
                os=mobile_os,
                screen_constraints=constraints,
                worker_id=worker_id,
                max_retries=0,
                timeout_ms=MOBILE_FINGERPRINT_TIMEOUT_MS,
            )

            if not fingerprint:
                reason_codes = ['generation_failed']
                violations = ['Fingerprint generation returned no value']
            else:
                context_opts = map_fingerprint_to_context_options(fingerprint)
                is_valid, reason_codes, violations = validate_fingerprint_consistency(
                    fingerprint,
                    context_opts,
                )
                emit_mobile_fingerprint_event(
                    worker_id=worker_id,
                    event_type='fingerprint_validation_result',
                    is_valid=is_valid,
                    violation_count=len(violations),
                    violations=violations,
                    reason='|'.join(reason_codes) if reason_codes else 'ok',
                )
                if is_valid:
                    break

            if attempt >= MOBILE_FINGERPRINT_MAX_REGEN_ATTEMPTS:
                fingerprint = None
                break

            emit_mobile_fingerprint_event(
                worker_id=worker_id,
                event_type='fingerprint_regeneration',
                reason='|'.join(reason_codes) if reason_codes else 'generation_failed',
                fallback_target='regenerate',
            )

        if not fingerprint:
            setup_result['fallback_reason'] = '|'.join(reason_codes) if reason_codes else 'preflight_failed'
            setup_result['validation_reason_codes'] = reason_codes
            emit_mobile_fingerprint_event(
                worker_id=worker_id,
                event_type='fingerprint_fallback_triggered',
                reason=setup_result['fallback_reason'],
                fallback_target='desktop',
                final_mode='desktop',
            )
            print(f"Worker {worker_id}: Mobile fingerprint preflight failed, continuing desktop flow")
            return setup_result

        fp_summary = get_fingerprint_summary(fingerprint)
        if MOBILE_FINGERPRINT_DRY_RUN:
            setup_result['fingerprint_mode'] = 'dry_run'
            emit_mobile_fingerprint_event(
                worker_id=worker_id,
                event_type='fingerprint_dry_run_completed',
                final_mode='desktop',
                browser_family=browser_family,
                os=mobile_os,
                **fp_summary,
            )
            print(f"Worker {worker_id}: Mobile fingerprint dry-run passed, desktop context retained")
            return setup_result

        setup_result['context_options'] = context_opts
        setup_result['fingerprint_mode'] = 'mobile'
        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type='mobile_context_ready',
            final_mode='mobile',
            browser_family=browser_family,
            os=mobile_os,
            **fp_summary,
        )
        print(f"Worker {worker_id}: Mobile fingerprint mode activated")
        return setup_result

    except Exception as e:
        print(f"Worker {worker_id}: Browser initialization error: {str(e)}")
        return None


async def cleanup_browser(browser, worker_id: int):
    """Clean up browser contexts and close the browser."""
    try:
        if not browser:
            return

        for context in browser.contexts:
            try:
                await context.close()
            except:
                pass

        try:
            await browser.close()
        except:
            pass

    except Exception as e:
        print(f"Worker {worker_id}: Error during browser cleanup: {str(e)}")
