"""
nexads/browser/setup.py
Browser initialization and cleanup using Camoufox.
"""

import random
import asyncio
import json
from typing import Optional, Dict, List
from urllib.parse import urlparse

from camoufox.async_api import AsyncCamoufox
from camoufox import DefaultAddons
from playwright.async_api import async_playwright
from browserforge.fingerprints import Screen
from playwright_stealth import Stealth

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

_PLAYWRIGHT_MANAGERS: Dict[int, object] = {}


def build_mobile_fingerprint_injection_script(
    fingerprint: dict, geoip_data: dict = None
) -> str:
    """Build init script that injects additional fingerprint fields on top of playwright-stealth."""
    payload_json = json.dumps(fingerprint, ensure_ascii=True)
    geoip_json = json.dumps(geoip_data or {}, ensure_ascii=True)
    return f"""
(() => {{
    const fp = {payload_json};
    const geoip = {geoip_json};
    window.__nexads_browserforge_fingerprint = fp;
    window.__nexads_geoip = geoip;

    const defineGetter = (obj, key, value) => {{
        try {{
            Object.defineProperty(obj, key, {{
                get: () => value,
                configurable: true,
            }});
        }} catch (e) {{}}
    }};

    const nav = fp.navigator || {{}};
    const scr = fp.screen || {{}};
    const battery = fp.battery || null;
    const pluginsData = fp.pluginsData || {{}};
    const media = fp.multimediaDevices || {{}};
    const videoCard = fp.videoCard || {{}};

    Object.keys(nav).forEach((key) => {{
        if (key === 'userAgentData' || key === 'extraProperties') return;
        defineGetter(navigator, key, nav[key]);
    }});

    if (nav.userAgentData) {{
        defineGetter(navigator, 'userAgentData', nav.userAgentData);
    }}
    if (nav.extraProperties && typeof nav.extraProperties === 'object') {{
        Object.keys(nav.extraProperties).forEach((k) => defineGetter(navigator, k, nav.extraProperties[k]));
    }}

    if (battery) {{
        navigator.getBattery = async () => battery;
    }}

    const pluginList = Array.isArray(pluginsData.plugins) ? pluginsData.plugins : [];
    const mimeList = Array.isArray(pluginsData.mimeTypes) ? pluginsData.mimeTypes : [];
    defineGetter(navigator, 'plugins', pluginList);
    defineGetter(navigator, 'mimeTypes', mimeList);

    if (scr && typeof scr === 'object') {{
        Object.keys(scr).forEach((key) => defineGetter(screen, key, scr[key]));
        if (typeof scr.devicePixelRatio !== 'undefined') {{
            defineGetter(window, 'devicePixelRatio', scr.devicePixelRatio);
        }}
        if (typeof scr.innerWidth !== 'undefined') defineGetter(window, 'innerWidth', scr.innerWidth);
        if (typeof scr.innerHeight !== 'undefined') defineGetter(window, 'innerHeight', scr.innerHeight);
        if (typeof scr.outerWidth !== 'undefined') defineGetter(window, 'outerWidth', scr.outerWidth);
        if (typeof scr.outerHeight !== 'undefined') defineGetter(window, 'outerHeight', scr.outerHeight);
        if (typeof scr.pageXOffset !== 'undefined') defineGetter(window, 'pageXOffset', scr.pageXOffset);
        if (typeof scr.pageYOffset !== 'undefined') defineGetter(window, 'pageYOffset', scr.pageYOffset);
        if (typeof scr.screenX !== 'undefined') defineGetter(window, 'screenX', scr.screenX);
        if (typeof scr.availWidth !== 'undefined') defineGetter(window, 'screenLeft', scr.availWidth);
    }}

    if (videoCard.vendor || videoCard.renderer) {{
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445 && videoCard.vendor) return videoCard.vendor;
            if (parameter === 37446 && videoCard.renderer) return videoCard.renderer;
            return getParameter.call(this, parameter);
        }};

        if (typeof WebGL2RenderingContext !== 'undefined') {{
            const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(parameter) {{
                if (parameter === 37445 && videoCard.vendor) return videoCard.vendor;
                if (parameter === 37446 && videoCard.renderer) return videoCard.renderer;
                return getParameter2.call(this, parameter);
            }};
        }}
    }}

    defineGetter(window, '__nexads_audio_codecs', fp.audioCodecs || {{}});
    defineGetter(window, '__nexads_video_codecs', fp.videoCodecs || {{}});
    defineGetter(window, '__nexads_fonts', fp.fonts || []);
    defineGetter(window, '__nexads_multimedia_devices', media);

    // --- STEALTH SCRIPTS ---
    // Hide webdriver property to avoid bot detection
    Object.defineProperty(navigator, 'webdriver', {{
        get: () => undefined,
        configurable: true
    }});
    try {{ Object.defineProperty(navigator, 'webdriver', {{ value: false }}); }} catch(e) {{}}

    // Remove all automation detection variables
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    delete window.callSelenium;
    delete window.cdc_qdCNJQlP;
    window.cdc_adoQpoasnfa76pfcZLmcfl_Array = undefined;
    window.cdc_adoQpoasnfa76pfcZLmcfl_Promise = undefined;
    window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol = undefined;
    window.callSelenium = undefined;
    window.cdc_qdCNJQlP = undefined;

    // Override chrome.runtime
    if (typeof chrome !== 'undefined') {{
        Object.defineProperty(chrome, 'runtime', {{
            get: () => undefined,
            configurable: true
        }});
    }}

    // Override permissions.query
    if (navigator.permissions && navigator.permissions.query) {{
        const origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = (params) => {{
            if (params.name === 'notifications') {{
                return Promise.resolve({{ state: 'default' }});
            }}
            if (params.name === 'geolocation') {{
                if (geoip && geoip.latitude && geoip.longitude) {{
                    return Promise.resolve({{ state: 'prompt', coords: {{ latitude: geoip.latitude, longitude: geoip.longitude, accuracy: 100 }}, timestamp: Date.now() }});
                }}
            }}
            return origQuery(params);
        }};
    }}

    // Fake navigator.pdfViewerEnabled
    defineGetter(navigator, 'pdfViewerEnabled', true);

    // Override plugins
    if (navigator.plugins && navigator.plugins.length === 0) {{
        const fakePlugins = [
            {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', 0: {{ type: 'application/pdf', suffixes: 'pdf' }} }},
            {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', 0: {{ type: 'application/x-google-chrome-pdf', suffixes: 'pdf' }} }},
            {{ name: 'Native Client', filename: 'internal-nacl-plugin', description: '', 0: {{ type: 'application/x-nacl', suffixes: 'nexe' }} }}
        ];
        defineGetter(navigator, 'plugins', fakePlugins);
        defineGetter(navigator, 'mimeTypes', [
            {{ type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: fakePlugins[0] }},
            {{ type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: '', enabledPlugin: fakePlugins[1] }}
        ]);
    }}

    // Override languages based on geoip
    if (geoip && geoip.locale) {{
        defineGetter(navigator, 'language', geoip.locale.split('-')[0]);
        defineGetter(navigator, 'languages', [geoip.locale, geoip.locale.split('-')[0], 'en']);
    }}

    // Override Date to match timezone
    if (geoip && geoip.timezone) {{
        try {{
            const tzMatch = geoip.timezone.match(/([^/]+)\/([^/]+)$/);
            if (tzMatch) {{
                const tzAbbr = tzMatch[2].replace(/_/g, ' ');
                defineGetter(Date.prototype, 'toTimeString', () => {{
                    return ` ${{tzAbbr}}`;
                }});
            }}
        }} catch(e) {{}}
    }}

    // Override connection API
    if (navigator.connection) {{
        defineGetter(navigator.connection, 'saveData', false);
        defineGetter(navigator.connection, 'effectiveType', '4g');
        defineGetter(navigator.connection, 'downlink', 10);
        defineGetter(navigator.connection, 'rtt', 50);
    }}

    // Override battery API if missing
    if (!navigator.getBattery) {{
        navigator.getBattery = async () => ({{
            charging: true,
            chargingTime: 0,
            dischargingTime: Infinity,
            level: 1.0,
            addEventListener: () => {{}},
            removeEventListener: () => {{}}
        }});
    }}

    // Override Notification.permission
    Object.defineProperty(Notification, 'permission', {{
        get: () => 'default',
        configurable: true
    }});

    // Override MediaQueryList
    if (typeof window.matchMedia === 'function') {{
        const origMatchMedia = window.matchMedia.bind(window);
        window.matchMedia = (query) => {{
            const result = origMatchMedia(query);
            Object.defineProperties(result, {{
                addListener: {{ value: () => {{}}, writable: true, configurable: true }},
                removeListener: {{ value: () => {{}}, writable: true, configurable: true }},
                addEventListener: {{ value: () => {{}}, writable: true, configurable: true }},
                removeEventListener: {{ value: () => {{}}, writable: true, configurable: true }}
            }});
            return result;
        }};
    }}

    // Override iframe sandbox detection
    try {{
        const origHTML = HTMLIFrameElement.prototype.hasOwnProperty;
        if (typeof origHTML === 'function') {{
            // Don't interfere with this
        }}
    }} catch(e) {{}}

    // Clear any performance metrics that might indicate automation
    if (window.performance) {{
        defineGetter(window.performance, 'memory', undefined);
    }}

    // Override getComputedStyle to avoid automation detection
    const origGetComputedStyle = window.getComputedStyle.bind(window);
    window.getComputedStyle = (elem, pseudo) => {{
        const style = origGetComputedStyle(elem, pseudo);
        // Ensure mozOsxnseline doesn't leak
        if (style) {{
            try {{ delete style.mozOsxInline; }} catch(e) {{}}
        }}
        return style;
    }};

    // --- ANTI-INCOGNITO DETECTION ---
    // Make storage APIs appear to work normally
    try {{
        if (typeof localStorage === 'undefined' || localStorage === null) {{
            const mockStorage = {{}};
            Object.defineProperty(window, 'localStorage', {{
                get: () => mockStorage,
                configurable: true
            }});
        }}
        
        // Ensure localStorage.setItem doesn't throw
        if (typeof Storage !== 'undefined') {{
            const origSetItem = Storage.prototype.setItem;
            Storage.prototype.setItem = function(key, value) {{
                try {{ origSetItem.call(this, key, value); }} catch(e) {{}}
            }};
        }}
    }} catch(e) {{}}

    // Override navigator.storage for privacy API
    if (navigator.storage && navigator.storage.estimate) {{
        const origEstimate = navigator.storage.estimate.bind(navigator.storage);
        navigator.storage.estimate = async () => {{
            const result = await origEstimate();
            return {{
                ...result,
                usage: result.usage || 1024 * 1024 * 5,
                quota: result.quota || 1024 * 1024 * 100
            }};
        }};
    }}

    // Fake navigator.cookieEnabled behavior
    defineGetter(navigator, 'cookieEnabled', true);

    // Fake WebSQL to appear non-incognito
    if (typeof window.openDatabase !== 'undefined') {{
        // openDatabase exists, which is a good sign
    }} else {{
        window.openDatabase = (name, version, displayName, estimatedSize, creationCallback) => {{
            return {{
                transaction: () => {{}}
            }};
        }};
    }}

    // Override indexedDB to appear normal
    if (typeof indexedDB === 'undefined') {{
        window.indexedDB = {{
            open: () => ({{ result: null, onsuccess: null, onerror: null }}),
            deleteDatabase: () => ({{}}),
            cmp: () => 0
        }};
    }}

    // Fake document.visibilityState
    defineGetter(document, 'visibilityState', 'visible');
    defineGetter(document, 'hidden', false);

    // Fake document.hasStorageAccess if available
    if (typeof document.hasStorageAccess === 'function') {{
        const origHasStorageAccess = document.hasStorageAccess.bind(document);
        document.hasStorageAccess = async () => {{
            try {{
                return await origHasStorageAccess();
            }} catch(e) {{
                return true;
            }}
        }};
    }}

    // Fake permissions for storage-access
    if (navigator.permissions && navigator.permissions.query) {{
        const origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = (params) => {{
            if (params.name === 'storage-access') {{
                return Promise.resolve({{ state: 'granted' }});
            }}
            return origQuery(params);
        }};
    }}

    // Fake battery again to ensure it's present
    if (!navigator.getBattery) {{
        Object.defineProperty(navigator, 'getBattery', {{
            value: async () => ({{
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1.0,
                addEventListener: () => {{}},
                removeEventListener: () => {{}}
            }}),
            configurable: true
        }});
    }}

    // Override HardwareConcurrency
    if (navigator.hardwareConcurrency !== undefined) {{
        defineGetter(navigator, 'hardwareConcurrency', 8);
    }}

    // Override deviceMemory
    if (navigator.deviceMemory !== undefined) {{
        defineGetter(navigator, 'deviceMemory', 8);
    }}

    // Remove privacy.resistFingerprinting indicator
    try {{
        delete navigator.globalPrivacyControl;
    }} catch(e) {{}}

    // Fake service worker
    Object.defineProperty(navigator, 'serviceWorker', {{
        get: () => {{
            return {{
                register: () => Promise.resolve({{}}),
                getRegistration: () => Promise.resolve(undefined),
                getRegistrations: () => Promise.resolve([]),
                ready: Promise.resolve({{}})
            }};
        }},
        configurable: true
    }});

    // Ensure SpeechSynthesis looks normal
    if (typeof speechSynthesis !== 'undefined') {{
        Object.defineProperty(window, 'speechSynthesis', {{
            get: () => (function() {{
                let _speaking = false;
                let _paused = false;
                let _pending = [];
                return {{
                    speak: (utterance) => {{ _pending.push(utterance); }},
                    cancel: () => {{ _pending = []; _speaking = false; }},
                    pause: () => {{ _paused = true; }},
                    resume: () => {{ _paused = false; }},
                    getVoices: () => [],
                    speaking: _speaking,
                    paused: _paused,
                    pending: _pending,
                    onvoiceschanged: null,
                    addEventListener: () => {{}},
                    removeEventListener: () => {{}},
                    dispatchEvent: () => true
                }};
            }})(),
            configurable: true
        }});
    }}
}})();
"""


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


async def _launch_mobile_playwright_browser(
    headless_mode,
    proxy_cfg: Optional[Dict[str, str]],
    browser_family: str,
    worker_id: int,
    geoip_data: Optional[dict] = None,
):
    """Launch Playwright browser for mobile sessions with stealth settings."""
    playwright_headless = False if headless_mode is False else True

    stealth_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
        "--allow-running-insecure-content",
    ]

    launch_kwargs = {
        "headless": playwright_headless,
        "args": stealth_args,
    }
    if proxy_cfg:
        launch_kwargs["proxy"] = proxy_cfg

    stealth_launch_kwargs = dict(launch_kwargs)

    stealth = Stealth()

    locale_override = None
    if geoip_data and geoip_data.get("locale"):
        locale_override = (geoip_data["locale"],)

    stealth_kwargs = {
        "navigator_languages_override": locale_override,
    }

    stealth_manager = stealth.use_async(async_playwright())
    pw = await stealth_manager.__aenter__()

    engine = pw.webkit if browser_family == "safari" else pw.chromium

    try:
        browser = await engine.launch(**stealth_launch_kwargs)
    except Exception as launch_error:
        if browser_family == "safari":
            emit_mobile_fingerprint_event(
                worker_id=worker_id,
                event_type="mobile_engine_fallback",
                strategy_mode="active",
                reason="webkit_launch_failed",
                reason_codes=["webkit_launch_failed"],
                fallback_target="chromium",
            )
            browser = await pw.chromium.launch(**stealth_launch_kwargs)
        else:
            await stealth_manager.__aexit__(None, None, None)
            raise launch_error

    _PLAYWRIGHT_MANAGERS[id(browser)] = (pw, stealth_manager, stealth_kwargs)
    return browser, stealth, stealth_kwargs


def map_fingerprint_to_context_options(fingerprint: Optional[dict]) -> Dict:
    """
    Map BrowserForge fingerprint fields to Playwright context options (Task 3).

    Args:
        fingerprint: BrowserForge Fingerprint object or None

    Returns:
        Dict of context_options for browser.new_context(**options)
    """
    if not isinstance(fingerprint, dict):
        return {}

    navigator = fingerprint.get("navigator")
    headers = fingerprint.get("headers")

    context_opts = {}

    if ua := _fp_get(navigator, "userAgent"):
        context_opts["user_agent"] = ua

    # Keep mobile identity broad; do not force viewport/screen dimensions.
    context_opts["is_mobile"] = True
    context_opts["has_touch"] = True

    if lang := _fp_get(navigator, "language"):
        context_opts["locale"] = lang

    safe_headers = {}
    if isinstance(headers, dict):
        for key, value in headers.items():
            if key is None or value is None:
                continue
            safe_headers[str(key)] = str(value)
    elif headers and hasattr(headers, "items"):
        for key, value in headers.items():
            if key is None or value is None:
                continue
            safe_headers[str(key)] = str(value)

    locale = context_opts.get("locale", "")
    if locale and "Accept-Language" not in safe_headers:
        safe_headers["Accept-Language"] = locale

    if safe_headers:
        context_opts["extra_http_headers"] = safe_headers

    return context_opts


def validate_fingerprint_consistency(
    fingerprint: Optional[dict], context_opts: Dict
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
            f"Impossible combo: iOS UA with maxTouchPoints={max_touch} (expected ≥5)"
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
            "context_options": {},
            "fingerprint_mode": "desktop",
            "fallback_reason": "",
            "validation_reason_codes": [],
            "fingerprint_injection_script": "",
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

        # Mobile path: Playwright browser engine + fingerprinted context options.
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
        if MOBILE_FINGERPRINT_ADVANCED_OVERRIDE_ENABLED:
            context_opts = dict(context_opts)

        if geoip_data:
            if geoip_data.get("locale"):
                context_opts["locale"] = geoip_data["locale"]
            if geoip_data.get("timezone"):
                context_opts["timezone_id"] = geoip_data["timezone"]
            accept_lang = geoip_data.get("locale", "en-US")
            context_opts["extra_http_headers"] = context_opts.get(
                "extra_http_headers", {}
            )
            context_opts["extra_http_headers"]["Accept-Language"] = accept_lang

        browser, stealth, stealth_kwargs = await _launch_mobile_playwright_browser(
            headless_mode=headless,
            proxy_cfg=proxy_cfg,
            browser_family=browser_family,
            worker_id=worker_id,
            geoip_data=geoip_data,
        )
        delay = get_random_delay_fn()
        await asyncio.sleep(delay)
        setup_result["browser"] = browser
        setup_result["stealth"] = stealth
        setup_result["stealth_kwargs"] = stealth_kwargs
        setup_result["context_options"] = context_opts
        setup_result["fingerprint_mode"] = "mobile"
        setup_result["geoip_data"] = geoip_data
        setup_result["fingerprint_injection_script"] = (
            build_mobile_fingerprint_injection_script(fingerprint, geoip_data)
        )
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
            f"Worker {worker_id}: Mobile fingerprint mode activated with playwright-stealth"
        )
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

        manager_data = _PLAYWRIGHT_MANAGERS.pop(id(browser), None)
        if manager_data:
            try:
                stealth_context = None
                pw = None
                if isinstance(manager_data, tuple):
                    if len(manager_data) >= 1:
                        pw = manager_data[0]
                    if len(manager_data) >= 2:
                        stealth_context = manager_data[1]
                else:
                    pw = manager_data
                if stealth_context:
                    await stealth_context.__aexit__(None, None, None)
                if pw:
                    await pw.stop()
            except:
                pass

    except Exception as e:
        print(f"Worker {worker_id}: Error during browser cleanup: {str(e)}")
