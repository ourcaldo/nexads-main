"""
app/navigation/instagram.py
Instagram referrer: igshid generation and direct header-based navigation.
"""

import random
import asyncio
import base64


def generate_igshid() -> str:
    """Generate a realistic Instagram Share ID.

    Real igshid values are base64-encoded identifiers, typically 15-25 chars.
    """
    num_bytes = random.randint(11, 18)
    raw = bytes(random.getrandbits(8) for _ in range(num_bytes))
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


async def navigate_instagram_referrer(page, target_url: str, worker_id: int,
                                      is_mobile: bool = False) -> bool:
    """Navigate to target with Instagram referer header and igshid parameter."""
    referer = "https://l.instagram.com/" if random.random() < 0.5 else "https://www.instagram.com/"

    print(f"Worker {worker_id}: Using Instagram referer")

    try:
        igshid = generate_igshid()
        separator = "&" if "?" in target_url else "?"
        url_with_igshid = f"{target_url}{separator}igsh={igshid}"

        await page.set_extra_http_headers({"referer": referer})
        await page.goto(url_with_igshid, timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.5, 3.0))
        await page.set_extra_http_headers({})

        print(f"Worker {worker_id}: Navigated with Instagram referer: {page.url}")
        return True

    except Exception as e:
        print(f"Worker {worker_id}: Instagram referrer navigation error: {str(e)}")
        try:
            await page.set_extra_http_headers({})
        except Exception:
            pass
        return False
