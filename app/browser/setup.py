"""
nexads/browser/setup.py
Browser initialization and cleanup using Camoufox.
"""

import random
import asyncio

from camoufox.async_api import AsyncCamoufox
from camoufox import DefaultAddons
from browserforge.fingerprints import Screen


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


async def configure_browser(config: dict, worker_id: int, get_random_delay_fn):
    """Configure and return a new Camoufox browser instance."""
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
