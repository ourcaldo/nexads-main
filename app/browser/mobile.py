"""
app/browser/mobile.py
Mobile device fingerprint generation using BrowserForge.
"""

import asyncio
import random
from typing import Optional, Tuple, List

from browserforge.fingerprints import FingerprintGenerator, Screen, Fingerprint

from app.core.telemetry import emit_mobile_fingerprint_event


async def generate_mobile_fingerprint(
    domain: str,
    browser_family: str,
    os: str,
    screen_constraints: dict,
    worker_id: int,
    max_retries: int = 1,
    timeout_ms: int = 5000,
    retry_count: int = 0
) -> Optional[Fingerprint]:
    """
    Generate a realistic mobile device fingerprint using BrowserForge.
    
    Args:
        domain: Target domain (for future locale matching)
        browser_family: "chrome", "safari", "firefox", "edge"
        os: "android" or "ios"
        screen_constraints: Dict with min_width, max_width, min_height, max_height
        worker_id: Worker ID for logging
        max_retries: Maximum retry attempts after the first generation attempt
        timeout_ms: Timeout for generation in milliseconds
        retry_count: Internal retry counter (do not set)
    
    Returns:
        Fingerprint dataclass (BrowserForge) or None on failure/fallback
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
        
        # Create Screen constraint from config
        screen = Screen(
            min_width=screen_constraints.get('min_width', 360),
            max_width=screen_constraints.get('max_width', 430),
            min_height=screen_constraints.get('min_height', 740),
            max_height=screen_constraints.get('max_height', 932)
        )
        
        # Generate fingerprint with timeout
        generator = FingerprintGenerator()
        
        # Run generation in asyncio with timeout
        import time
        start_time = time.time()
        fingerprint = await asyncio.wait_for(
            asyncio.to_thread(
                generator.generate,
                browser=browser_family,
                os=os,
                device='mobile',
                screen=screen
            ),
            timeout=timeout_ms / 1000.0
        )
        generation_ms = int((time.time() - start_time) * 1000)
        
        # Emit success event with profile summary
        ua_snippet = fingerprint.navigator.get('userAgent', 'N/A')[:60] if fingerprint.navigator else 'N/A'
        emit_mobile_fingerprint_event(
            worker_id=worker_id,
            event_type='profile_generated',
            browser_family=browser_family,
            os=os,
            ua_snippet=ua_snippet,
            platform=fingerprint.navigator.get('platform', 'N/A') if fingerprint.navigator else 'N/A',
            viewport=f"{fingerprint.screen.get('width', 0)}x{fingerprint.screen.get('height', 0)}" if fingerprint.screen else 'N/A',
            dpr=fingerprint.screen.get('devicePixelRatio', 1) if fingerprint.screen else 1,
            generation_ms=generation_ms
        )
        
        print(f"Worker {worker_id}: Mobile fingerprint generated ({browser_family}/{os}, "
              f"ua_snippet={ua_snippet}...)")
        return fingerprint
        
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


def get_fingerprint_summary(fingerprint: Optional[Fingerprint]) -> dict:
    """
    Extract summary fields from a BrowserForge fingerprint for logging/telemetry.
    
    Args:
        fingerprint: Fingerprint object or None
    
    Returns:
        Dict with ua_snippet, platform, viewport, dpr, locale, or empty dict if None
    """
    if not fingerprint:
        return {}
    
    navigator = fingerprint.navigator or {}
    screen = fingerprint.screen or {}
    headers = fingerprint.headers or {}
    
    ua = navigator.get('userAgent', 'N/A')
    ua_snippet = ua[:60] if ua else 'N/A'
    
    return {
        'ua_snippet': ua_snippet,
        'platform': navigator.get('platform', 'N/A'),
        'viewport': f"{screen.get('width', 0)}x{screen.get('height', 0)}",
        'dpr': screen.get('devicePixelRatio', 1),
        'locale': navigator.get('language', 'en'),
        'max_touch_points': navigator.get('maxTouchPoints', 0),
        'sec_ch_ua_mobile': headers.get('Sec-CH-UA-Mobile', 'N/A')
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


