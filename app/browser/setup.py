"""
nexads/browser/setup.py
Browser initialization and cleanup using Camoufox.
"""

import random
import asyncio
from typing import Optional, Tuple, Dict, List

from camoufox.async_api import AsyncCamoufox
from camoufox import DefaultAddons
from browserforge.fingerprints import Screen, Fingerprint

from app.browser.mobile import (
    generate_mobile_fingerprint,
    get_fingerprint_summary,
    parse_mobile_constraints,
    select_mobile_profile_params
)
from app.core.telemetry import emit_mobile_profile_event


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


def map_fingerprint_to_context_options(fingerprint: Optional[Fingerprint], config: dict) -> Dict:
    """
    Map BrowserForge fingerprint fields to Playwright context options (Task 3).
    
    Args:
        fingerprint: BrowserForge Fingerprint object or None
        config: Config dict
    
    Returns:
        Dict of context_options for browser.new_context(**options)
    """
    if not fingerprint:
        return {}
    
    navigator = fingerprint.navigator or {}
    screen = fingerprint.screen or {}
    headers = fingerprint.headers or {}
    
    # Core mappings: native Playwright context options
    context_opts = {}
    
    # User-Agent
    if ua := navigator.get('userAgent'):
        context_opts['user_agent'] = ua
    
    # Viewport and device scale factor
    width = screen.get('width', 360)
    height = screen.get('height', 740)
    context_opts['viewport'] = {'width': width, 'height': height}
    
    if dpr := screen.get('devicePixelRatio'):
        context_opts['device_scale_factor'] = float(dpr)
    
    # Mobile and touch flags
    context_opts['is_mobile'] = True  # Always True since we're in mobile path
    max_touch = navigator.get('maxTouchPoints', 5)
    context_opts['has_touch'] = max_touch > 0
    
    # Locale / Language
    if lang := navigator.get('language'):
        context_opts['locale'] = lang
    
    # Extra HTTP headers
    if headers:
        # Filter headers to safe subset (avoid Content-Length, Host, etc.)
        safe_headers = {}
        header_keys = [
            'User-Agent', 'Accept-Language', 'Accept', 'Accept-Encoding',
            'Sec-Fetch-Site', 'Sec-Fetch-Mode', 'Sec-Fetch-Dest',
            'Sec-CH-UA', 'Sec-CH-UA-Mobile', 'Sec-CH-UA-Platform',
            'Upgrade-Insecure-Requests'
        ]
        for key in header_keys:
            if key in headers and headers[key]:
                safe_headers[key] = str(headers[key])
        
        if safe_headers:
            context_opts['extra_http_headers'] = safe_headers
    
    return context_opts


def validate_profile_consistency(
    fingerprint: Optional[Fingerprint],
    context_opts: Dict,
    worker_id: int
) -> Tuple[bool, List[str]]:
    """
    Validate consistency of mobile profile fingerprint (Task 4).
    
    Args:
        fingerprint: BrowserForge Fingerprint object or None
        context_opts: Mapped context options
        worker_id: Worker ID for logging
    
    Returns:
        Tuple of (is_valid: bool, violations: List[str])
    """
    violations = []
    
    if not fingerprint:
        return True, []  # No fingerprint, nothing to validate
    
    navigator = fingerprint.navigator or {}
    ua = navigator.get('userAgent', '')
    platform = navigator.get('platform', '')
    
    # Rule 1: Mobile flag consistency
    has_mobile_in_ua = 'Mobile' in ua
    is_mobile_flag = context_opts.get('is_mobile', False)
    if has_mobile_in_ua and not is_mobile_flag:
        violations.append(f"Mobile flag mismatch: UA has 'Mobile' but is_mobile=False")
    if not has_mobile_in_ua and is_mobile_flag:
        # Less strict: some mobile UAs don't have Mobile keyword
        pass
    
    # Rule 2: Touch consistency
    max_touch = navigator.get('maxTouchPoints', 0)
    has_touch_flag = context_opts.get('has_touch', False)
    if max_touch > 0 and not has_touch_flag:
        violations.append(f"Touch flag mismatch: maxTouchPoints={max_touch} but has_touch=False")
    
    # Rule 3: Platform realism
    if 'Android' in ua:
        # Android should have Linux platform
        if platform and not platform.startswith('Linux'):
            violations.append(f"Platform mismatch: Android UA found with platform={platform} (expected Linux)")
    elif 'iPhone' in ua or 'iPad' in ua:
        # iOS should have iPhone or iPad platform
        if platform and platform not in ['iPhone', 'iPad']:
            violations.append(f"Platform mismatch: iOS UA found with platform={platform} (expected iPhone/iPad)")
    
    # Rule 4: Impossible combos
    if 'Android' in ua and 'Mobile' not in ua:
        # Android typically includes Mobile in UA
        violations.append(f"Impossible combo: Android UA without 'Mobile' keyword")
    
    if max_touch < 5 and ('iPhone' in ua or 'iPad' in ua):
        # iOS devices have at least 5 touch points (typically)
        violations.append(f"Impossible combo: iOS UA with maxTouchPoints={max_touch} (expected ≥5)")
    
    is_valid = len(violations) == 0
    
    # Emit telemetry event
    emit_mobile_profile_event(
        worker_id=worker_id,
        event_type='profile_validation_result',
        is_valid=is_valid,
        violation_count=len(violations),
        violations=violations if violations else None
    )
    
    if not is_valid:
        print(f"Worker {worker_id}: Profile validation failed ({len(violations)} violations)")
    
    return is_valid, violations


async def configure_mobile_browser(
    config: dict,
    worker_id: int,
    get_random_delay_fn,
    target_domain: str = "example.com"
) -> Optional[Tuple]:
    """
    Configure and return mobile Camoufox browser context (Task 2 mobile branch).
    
    Args:
        config: Config dict with mobile profile settings
        worker_id: Worker ID for logging
        get_random_delay_fn: Callable that returns random delay in seconds
        target_domain: Target domain (for future enhancements)
    
    Returns:
        Tuple of (browser, context) or (None, None) on failure
    """
    try:
        # --- Proxy Setup ---
        proxy = None
        if config['proxy']['credentials']:
            proxy = config['proxy']['credentials']
        elif config['proxy']['file']:
            with open(config['proxy']['file'], 'r') as f:
                proxies = [line.strip() for line in f if line.strip()]
            if proxies:
                proxy = random.choice(proxies)

        # --- Headless Mode ---
        headless = True
        if config['browser']['headless_mode'] == 'False':
            headless = False
        elif config['browser']['headless_mode'] == 'virtual':
            headless = 'virtual'

        os_fingerprint = random.choice(config['os_fingerprint'])

        # --- Mobile Screen Constraint ---
        screen = Screen(max_width=430, max_height=932)

        # --- Browser Launch Options ---
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

        # --- Launch Browser ---
        browser = await AsyncCamoufox(**options).start()
        print(f"Worker {worker_id}: Mobile browser launched")
        
        delay = get_random_delay_fn()
        await asyncio.sleep(delay)

        # --- Generate Mobile Fingerprint ---
        constraints = parse_mobile_constraints(config)
        browser_family, mobile_os = select_mobile_profile_params(config)
        
        fingerprint = await generate_mobile_fingerprint(
            domain=target_domain,
            browser_family=browser_family,
            os=mobile_os,
            screen_constraints=constraints,
            config=config,
            worker_id=worker_id
        )
        
        fp_summary = get_fingerprint_summary(fingerprint)

        # --- Validate Consistency ---
        if fingerprint:
            context_opts = map_fingerprint_to_context_options(fingerprint, config)
            is_valid, violations = validate_profile_consistency(fingerprint, context_opts, worker_id)
            
            if not is_valid:
                policy = config.get('profile_consistency_policy', 'block')
                print(f"Worker {worker_id}: Profile validation failed: {violations}")
                if policy == 'block':
                    print(f"Worker {worker_id}: Falling back to desktop (validation policy=block)")
                    emit_mobile_profile_event(
                        worker_id=worker_id,
                        event_type='profile_fallback_triggered',
                        reason='validation_failed',
                        fallback_target='desktop'
                    )
                    await cleanup_browser(browser, worker_id)
                    return None  # Signal to fall back to desktop
        else:
            # No fingerprint generated (timeout/error)
            print(f"Worker {worker_id}: No fingerprint generated, falling back to desktop")
            emit_mobile_profile_event(
                worker_id=worker_id,
                event_type='profile_fallback_triggered',
                reason='generation_failed',
                fallback_target='desktop'
            )
            await cleanup_browser(browser, worker_id)
            return None

        # --- Create Context with Mobile Profile ---
        context = await browser.new_context(**context_opts)
        fp_summary = get_fingerprint_summary(fingerprint)
        print(f"Worker {worker_id}: Mobile context created with profile: {fp_summary}")
        
        emit_mobile_profile_event(
            worker_id=worker_id,
            event_type='context_created',
            final_mode='mobile',
            browser_family=browser_family,
            os=mobile_os,
            **fp_summary
        )

        return (browser, context)

    except Exception as e:
        print(f"Worker {worker_id}: Mobile browser configuration error: {str(e)}")
        return None


async def configure_browser(config: dict, worker_id: int, get_random_delay_fn):
    """Configure and return a new Camoufox browser instance."""
    try:
        # --- Mobile Profile Branching (Task 2) ---
        profile_strategy = config.get('profile_strategy', 'desktop-only')
        rollout_pct = config.get('profile_strategy_rollout_percentage', 0)
        
        if profile_strategy in ['mobile-enabled', 'dry-run'] and rollout_pct > 0:
            # Probabilistically select mobile vs desktop based on rollout percentage
            if random.randint(1, 100) <= rollout_pct:
                print(f"Worker {worker_id}: Mobile profile selected (rollout={rollout_pct}%)")
                mobile_result = await configure_mobile_browser(config, worker_id, get_random_delay_fn)
                
                if mobile_result is not None:
                    # Mobile succeeded, use it
                    return mobile_result
                else:
                    # Mobile failed or returned None, fall back to desktop
                    print(f"Worker {worker_id}: Mobile configuration failed, falling back to desktop")
        
        # --- Desktop Path (Original Logic) ---
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
        return browser

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
