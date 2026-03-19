"""
app/browser/mobile.py
Mobile device fingerprint generation using BrowserForge.
"""

import asyncio
import random
from typing import Optional, Tuple, List

from browserforge.fingerprints import FingerprintGenerator

from app.core.telemetry import emit_mobile_fingerprint_event


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
        'userAgent': 'user_agent',
        'maxTouchPoints': 'max_touch_points',
        'devicePixelRatio': 'device_pixel_ratio',
    }
    alias = aliases.get(key)
    if alias and hasattr(obj, alias):
        value = getattr(obj, alias)
        return default if value is None else value

    return default


async def generate_mobile_fingerprint(
    domain: str,
    browser_family: str,
    os: str,
    screen_constraints: dict,
    worker_id: int,
    max_retries: int = 1,
    timeout_ms: int = 5000,
    retry_count: int = 0
) -> Optional[dict]:
    """
    Generate a full BrowserForge mobile fingerprint payload.
    
    Args:
        domain: Target domain (currently informational)
        browser_family: "chrome", "safari", "firefox", "edge"
        os: "android" or "ios"
        screen_constraints: Deprecated, ignored (kept for API compatibility)
        worker_id: Worker ID for logging
        max_retries: Maximum retry attempts after the first generation attempt
        timeout_ms: Timeout for generation in milliseconds
        retry_count: Internal retry counter (do not set)
    
    Returns:
        Dict containing full BrowserForge fingerprint payload
    """
    try:
        retry_policy = 'regenerate_once'
        
        # Emit start event
        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type='profile_generation_started',
            browser_family=browser_family,
            os=os
        )
        
        generator = FingerprintGenerator()
        
        # Run generation in asyncio with timeout
        import time
        start_time = time.time()
        fp_obj = await asyncio.wait_for(
            asyncio.to_thread(
                generator.generate,
                browser=browser_family,
                os=os,
                device='mobile',
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
            if hasattr(obj, 'model_dump'):
                try:
                    return _to_plain(obj.model_dump())
                except Exception:
                    pass
            if hasattr(obj, '__dict__'):
                return {
                    str(k): _to_plain(v)
                    for k, v in vars(obj).items()
                    if not str(k).startswith('_')
                }
            return str(obj)

        mobile_identity = _to_plain(fp_obj)
        if not isinstance(mobile_identity, dict):
            raise ValueError('BrowserForge fingerprint conversion failed')

        headers = mobile_identity.get('headers', {})
        if isinstance(headers, dict):
            mobile_identity['headers'] = {
                str(k): str(v)
                for k, v in headers.items()
                if k is not None and v is not None
            }
        
        # Emit success event with profile summary
        navigator = mobile_identity.get('navigator', {})
        ua_snippet = str(_fp_get(navigator, 'userAgent', 'N/A'))[:60]
        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type='profile_generated',
            browser_family=browser_family,
            os=os,
            ua_snippet=ua_snippet,
            platform=_fp_get(navigator, 'platform', 'N/A'),
            locale=_fp_get(navigator, 'language', 'en-US'),
            generation_ms=generation_ms
        )
        
        print(f"Worker {worker_id}: Mobile fingerprint generated ({browser_family}/{os}, "
              f"ua_snippet={ua_snippet}...)")
        return mobile_identity
        
    except asyncio.TimeoutError as e:
        print(f"Worker {worker_id}: Fingerprint generation timeout after {timeout_ms}ms (attempt {retry_count + 1})")
        
        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type='profile_generation_started',
            browser_family=browser_family,
            os=os,
            reason=f'Timeout after {timeout_ms}ms'
        )
        
        if retry_policy == 'regenerate_once' and retry_count < max_retries:
            print(f"Worker {worker_id}: Retrying fingerprint generation...")
            await asyncio.sleep(random.uniform(0.5, 1.0))
            return await generate_mobile_fingerprint(
                domain, browser_family, os, screen_constraints, worker_id,
                max_retries=max_retries,
                timeout_ms=timeout_ms,
                retry_count=retry_count + 1
            )
        return None
        
    except Exception as e:
        print(f"Worker {worker_id}: Fingerprint generation error: {str(e)} (attempt {retry_count + 1})")
        
        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type='profile_generation_started',
            browser_family=browser_family,
            os=os,
            reason=f'Error: {str(e)}'
        )
        
        if retry_policy == 'regenerate_once' and retry_count < max_retries:
            print(f"Worker {worker_id}: Retrying fingerprint generation after error...")
            await asyncio.sleep(random.uniform(0.5, 1.0))
            return await generate_mobile_fingerprint(
                domain, browser_family, os, screen_constraints, worker_id,
                max_retries=max_retries,
                timeout_ms=timeout_ms,
                retry_count=retry_count + 1
            )
        return None


def get_fingerprint_summary(fingerprint: Optional[dict]) -> dict:
    """
    Extract summary fields from a BrowserForge fingerprint for logging/telemetry.
    
    Args:
        fingerprint: Fingerprint object or None
    
    Returns:
        Dict with ua_snippet, platform, viewport, dpr, locale, or empty dict if None
    """
    if not fingerprint:
        return {}
    
    navigator = (fingerprint or {}).get('navigator') if isinstance(fingerprint, dict) else None
    headers = (fingerprint or {}).get('headers') if isinstance(fingerprint, dict) else None
    
    ua = str(_fp_get(navigator, 'userAgent', 'N/A'))
    ua_snippet = ua[:60] if ua else 'N/A'

    if isinstance(headers, dict):
        sec_ch_ua_mobile = headers.get('Sec-CH-UA-Mobile', 'N/A')
    elif hasattr(headers, 'get'):
        sec_ch_ua_mobile = headers.get('Sec-CH-UA-Mobile', 'N/A')
    else:
        sec_ch_ua_mobile = 'N/A'
    
    return {
        'ua_snippet': ua_snippet,
        'platform': _fp_get(navigator, 'platform', 'N/A'),
        'locale': _fp_get(navigator, 'language', 'en'),
        'max_touch_points': _fp_get(navigator, 'maxTouchPoints', 0),
        'sec_ch_ua_mobile': sec_ch_ua_mobile
    }


def parse_mobile_constraints(hardcoded_bounds: dict | None = None) -> dict:
    """
    Extract and validate mobile constraint bounds from config.
    
    Args:
        hardcoded_bounds: Optional hardcoded mobile bounds
    
    Returns:
        Dict with min_width, max_width, min_height, max_height (validated)
    """
    screen = hardcoded_bounds or {}
    
    return {
        'min_width': max(360, screen.get('min_width', 360)),
        'max_width': min(430, screen.get('max_width', 430)),
        'min_height': max(740, screen.get('min_height', 740)),
        'max_height': min(932, screen.get('max_height', 932)),
    }


def select_mobile_fingerprint_params(
    browsers: List[str] | None = None,
    os_list: List[str] | None = None,
) -> Tuple[str, str]:
    """
    Select random browser family and OS from mobile_constraints config.
    
    Args:
        browsers: Optional browser family candidates
        os_list: Optional OS candidates
    
    Returns:
        Tuple of (browser_family, os) e.g., ("chrome", "android")
    """
    browsers = browsers or ['chrome', 'safari']
    os_list = os_list or ['android', 'ios']

    candidate_pairs = [
        ('chrome', 'android'),
        ('safari', 'ios'),
    ]
    valid_pairs = [
        pair for pair in candidate_pairs
        if pair[0] in browsers and pair[1] in os_list
    ]

    if valid_pairs:
        return random.choice(valid_pairs)

    # Stable fallback when caller passes restrictive lists.
    return 'chrome', 'android'


