"""
nexads/browser/setup.py
Browser initialization and cleanup using Camoufox.
"""

import random
import asyncio

from camoufox.async_api import AsyncCamoufox
from camoufox import DefaultAddons
from browserforge.fingerprints import Screen


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

        screen = Screen(max_width=2800, max_height=2080) if device_type == 'mobile' \
                else Screen(max_width=7680, max_height=4320)

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
            if '@' in proxy:
                auth, server = proxy.split('@')
                user, pwd = auth.split(':')
                host, port = server.split(':')
                options['proxy'] = {
                    'server': f"{proxy_type}://{host}:{port}",
                    'username': user,
                    'password': pwd
                }
            else:
                host, port = proxy.split(':')
                options['proxy'] = {
                    'server': f"{proxy_type}://{host}:{port}",
                    'username': None,
                    'password': None
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
