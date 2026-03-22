"""
CloakBrowser standalone test.
Tests stealth quality against detection sites using a proxy from proxy.txt.

Usage:
    python tests/test_cloakbrowser.py
    python tests/test_cloakbrowser.py --headed     # see the browser window
    python tests/test_cloakbrowser.py --no-proxy   # run without proxy
"""

import asyncio
import random
import sys
import time

# Parse proxy from proxy.txt (format: host:port:user:pass)
def load_random_proxy(path="proxy.txt"):
    with open(path, "r") as f:
        lines = [l.strip() for l in f if l.strip()]
    line = random.choice(lines)
    parts = line.split(":")
    if len(parts) == 4:
        host, port, user, passwd = parts
        return f"http://{user}:{passwd}@{host}:{port}"
    elif len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    else:
        raise ValueError(f"Unexpected proxy format: {line}")


async def main():
    from cloakbrowser import launch_async

    headed = "--headed" in sys.argv
    no_proxy = "--no-proxy" in sys.argv

    proxy_url = None
    if not no_proxy:
        proxy_url = load_random_proxy()
        print(f"Using proxy: {proxy_url[:40]}...")

    print(f"Launching CloakBrowser (headed={headed}, proxy={'yes' if proxy_url else 'no'})...")

    launch_kwargs = {
        "headless": not headed,
        "humanize": True,
    }
    if proxy_url:
        launch_kwargs["proxy"] = proxy_url

    browser = await launch_async(**launch_kwargs)
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = await context.new_page()

    # --- Test 1: BrowserScan ---
    print("\n=== Test 1: BrowserScan (browserscan.net) ===")
    try:
        await page.goto("https://www.browserscan.net/", timeout=60000)
        await asyncio.sleep(15)  # let it analyze
        screenshot_path = "tests/cloakbrowser_browserscan.png"
        await page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")

        # Try to extract the bot detection result
        try:
            score_el = await page.query_selector(".bot-detection-result, .score, [class*='score'], [class*='result']")
            if score_el:
                text = await score_el.inner_text()
                print(f"Detection result: {text}")
        except Exception:
            pass
    except Exception as e:
        print(f"BrowserScan failed: {e}")

    # --- Test 2: bot.incolumitas.com ---
    print("\n=== Test 2: bot.incolumitas.com ===")
    try:
        await page.goto("https://bot.incolumitas.com/", timeout=60000)
        await asyncio.sleep(12)
        screenshot_path = "tests/cloakbrowser_incolumitas.png"
        await page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")
    except Exception as e:
        print(f"Incolumitas failed: {e}")

    # --- Test 3: deviceandbrowserinfo.com ---
    print("\n=== Test 3: deviceandbrowserinfo.com ===")
    try:
        await page.goto("https://deviceandbrowserinfo.com/info_device", timeout=60000)
        await asyncio.sleep(10)
        screenshot_path = "tests/cloakbrowser_deviceinfo.png"
        await page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")
    except Exception as e:
        print(f"DeviceInfo failed: {e}")

    # --- Test 4: iphey.com ---
    print("\n=== Test 4: iphey.com ===")
    try:
        await page.goto("https://iphey.com/", timeout=60000)
        await asyncio.sleep(12)
        screenshot_path = "tests/cloakbrowser_iphey.png"
        await page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")

        try:
            result_el = await page.query_selector(".trustworthy:not(.hide)")
            if result_el:
                text = await result_el.inner_text()
                print(f"Iphey result: {text}")
        except Exception:
            pass
    except Exception as e:
        print(f"Iphey failed: {e}")

    # --- Test 5: Target site (camarjaya.co.id) ---
    print("\n=== Test 5: Target site (app.camarjaya.co.id) ===")
    try:
        await page.goto("https://app.camarjaya.co.id/", timeout=60000)
        await asyncio.sleep(8)
        screenshot_path = "tests/cloakbrowser_target.png"
        await page.screenshot(path=screenshot_path, full_page=False)
        print(f"Screenshot saved: {screenshot_path}")
        print(f"Page title: {await page.title()}")
        print(f"Page URL: {page.url}")
    except Exception as e:
        print(f"Target site failed: {e}")

    # --- Fingerprint info ---
    print("\n=== Fingerprint Summary ===")
    try:
        info = await page.evaluate("""() => ({
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            webdriver: navigator.webdriver,
            languages: navigator.languages,
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory,
            maxTouchPoints: navigator.maxTouchPoints,
            plugins: navigator.plugins.length,
            windowChrome: typeof window.chrome,
            screenW: screen.width,
            screenH: screen.height,
        })""")
        for k, v in info.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"Could not read fingerprint: {e}")

    print("\n=== Done ===")
    print("Check the screenshots in tests/ folder.")

    if headed:
        print("Browser is open. Press Ctrl+C to close.")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
