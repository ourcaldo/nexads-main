"""
CloakBrowser mobile test v3.

Fixes: OS mismatch, incognito, timezone, GPU consistency.

Usage:
    python tests/test_cloakbrowser_mobile.py
"""

import asyncio
import random
import tempfile
import os


def load_random_proxy(path="proxy.txt"):
    with open(path, "r") as f:
        lines = [l.strip() for l in f if l.strip()]
    line = random.choice(lines)
    parts = line.split(":")
    host, port, user, passwd = parts[0], parts[1], parts[2], parts[3]
    return f"http://{user}:{passwd}@{host}:{port}"


async def main():
    from cloakbrowser import launch_persistent_context_async

    proxy_url = load_random_proxy()
    print(f"Proxy: {proxy_url[:40]}...")

    profile_dir = os.path.join(tempfile.gettempdir(), "cloakbrowser_mobile_v3")
    os.makedirs(profile_dir, exist_ok=True)
    print(f"Profile dir: {profile_dir}")

    context = await launch_persistent_context_async(
        profile_dir,
        headless=False,
        proxy=proxy_url,
        geoip=True,
        viewport={"width": 412, "height": 915},
        user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.7632.159 Mobile Safari/537.36",
        is_mobile=True,
        has_touch=True,
        device_scale_factor=2.625,
        args=[
            # Android platform — overrides default windows
            "--fingerprint-platform=android",
            # Mobile GPU consistent with Android (Qualcomm Adreno)
            "--fingerprint-gpu-vendor=Qualcomm",
            "--fingerprint-gpu-renderer=ANGLE (Qualcomm, Adreno (TM) 730, OpenGL ES 3.2)",
            # Screen matching mobile viewport
            "--fingerprint-screen-width=412",
            "--fingerprint-screen-height=915",
            # Fix incognito detection — raise storage quota
            "--fingerprint-storage-quota=5000",
            # Mobile hardware
            "--fingerprint-hardware-concurrency=8",
            "--fingerprint-device-memory=8",
        ],
    )

    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto("https://www.browserscan.net/", timeout=60000)

    print("Browser is open. Explore freely. Press Ctrl+C to close.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass

    await context.close()


if __name__ == "__main__":
    asyncio.run(main())
