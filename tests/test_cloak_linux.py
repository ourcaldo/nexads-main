import asyncio
import random

def load_proxy():
    with open("/home/nexdev/nexads/proxy.txt", "r") as f:
        lines = [l.strip() for l in f if l.strip()]
    line = random.choice(lines)
    parts = line.split(":")
    return "http://{}:{}@{}:{}".format(parts[2], parts[3], parts[0], parts[1])

async def main():
    from cloakbrowser import launch_persistent_context_async

    proxy_url = load_proxy()
    print("Proxy: {}...".format(proxy_url[:40]))

    profile_dir = "/tmp/cloakbrowser_desktop_final"

    context = await launch_persistent_context_async(
        profile_dir,
        headless=False,
        proxy=proxy_url,
        geoip=True,
        args=["--fingerprint-storage-quota=5000"],
    )

    page = context.pages[0] if context.pages else await context.new_page()

    print("Loading browserscan.net...")
    await page.goto("https://www.browserscan.net/", timeout=90000)
    print("Waiting 25s...")
    await asyncio.sleep(25)

    await page.screenshot(path="/tmp/cloak_final_top.png", full_page=False)
    print("Top screenshot saved")

    info = await page.evaluate(
        "() => ({"
        "  ua: navigator.userAgent,"
        "  platform: navigator.platform,"
        "  webdriver: navigator.webdriver,"
        "  quota: 0"
        "})"
    )
    print("UA: " + str(info.get("ua", "")))
    print("Platform: " + str(info.get("platform", "")))
    print("Webdriver: " + str(info.get("webdriver", "")))

    quota = await page.evaluate(
        "async () => {"
        "  const est = await navigator.storage.estimate();"
        "  return (est.quota / 1024 / 1024 / 1024).toFixed(2);"
        "}"
    )
    print("Storage quota: " + str(quota) + " GB")

    for scroll_y, name in [(700, "score"), (1300, "ded1"), (1900, "ded2"), (2500, "ded3")]:
        await page.evaluate("window.scrollTo(0, {})".format(scroll_y))
        await asyncio.sleep(3)
        await page.screenshot(path="/tmp/cloak_final_{}.png".format(name), full_page=False)
        print("Screenshot: " + name)

    await context.close()
    print("Done!")

asyncio.run(main())
