"""
nexads/browser/geoip.py
GeoIP lookup to get timezone, locale, and language based on proxy IP.
"""

import asyncio
import json
import random
from typing import Optional

LANGUAGE_MAP = {
    "US": ("en", "en-US"),
    "GB": ("en", "en-GB"),
    "CA": ("en", "en-CA"),
    "AU": ("en", "en-AU"),
    "DE": ("de", "de-DE"),
    "FR": ("fr", "fr-FR"),
    "ES": ("es", "es-ES"),
    "IT": ("it", "it-IT"),
    "NL": ("nl", "nl-NL"),
    "PL": ("pl", "pl-PL"),
    "BR": ("pt", "pt-BR"),
    "PT": ("pt", "pt-PT"),
    "RU": ("ru", "ru-RU"),
    "JP": ("ja", "ja-JP"),
    "KR": ("ko", "ko-KR"),
    "CN": ("zh", "zh-CN"),
    "TW": ("zh", "zh-TW"),
    "IN": ("hi", "hi-IN"),
    "ID": ("id", "id-ID"),
    "TH": ("th", "th-TH"),
    "VN": ("vi", "vi-VN"),
    "TR": ("tr", "tr-TR"),
    "SA": ("ar", "ar-SA"),
    "AE": ("ar", "ar-AE"),
    "EG": ("ar", "ar-EG"),
    "MX": ("es", "es-MX"),
    "AR": ("es", "es-AR"),
    "CL": ("es", "es-CL"),
    "CO": ("es", "es-CO"),
    "NG": ("en", "en-NG"),
    "ZA": ("en", "en-ZA"),
    "KE": ("en", "en-KE"),
    "NZ": ("en", "en-NZ"),
    "SG": ("en", "en-SG"),
    "MY": ("ms", "ms-MY"),
    "PH": ("en", "en-PH"),
    "PK": ("ur", "ur-PK"),
    "BD": ("bn", "bn-BD"),
    "IR": ("fa", "fa-IR"),
    "IL": ("he", "he-IL"),
    "RO": ("ro", "ro-RO"),
    "HU": ("hu", "hu-HU"),
    "CZ": ("cs", "cs-CZ"),
    "GR": ("el", "el-GR"),
    "SE": ("sv", "sv-SE"),
    "NO": ("no", "no-NO"),
    "DK": ("da", "da-DK"),
    "FI": ("fi", "fi-FI"),
    "AT": ("de", "de-AT"),
    "CH": ("de", "de-CH"),
    "BE": ("nl", "nl-BE"),
    "IE": ("en", "en-IE"),
    "UA": ("uk", "uk-UA"),
}

TIMEZONE_MAP = {
    "US": {
        "WA": "America/Los_Angeles",
        "OR": "America/Los_Angeles",
        "CA": "America/Los_Angeles",
        "NV": "America/Los_Angeles",
        "AZ": "America/Phoenix",
        "UT": "America/Denver",
        "CO": "America/Denver",
        "NM": "America/Denver",
        "TX": "America/Chicago",
        "OK": "America/Chicago",
        "KS": "America/Chicago",
        "NE": "America/Chicago",
        "IA": "America/Chicago",
        "IL": "America/Chicago",
        "MO": "America/Chicago",
        "MN": "America/Chicago",
        "WI": "America/Chicago",
        "MI": "America/Detroit",
        "IN": "America/Indiana/Indianapolis",
        "OH": "America/New_York",
        "PA": "America/New_York",
        "NY": "America/New_York",
        "NJ": "America/New_York",
        "CT": "America/New_York",
        "MA": "America/New_York",
        "FL": "America/New_York",
        "GA": "America/New_York",
        "NC": "America/New_York",
        "SC": "America/New_York",
        "VA": "America/New_York",
        "MD": "America/New_York",
        "DC": "America/New_York",
        "HI": "Pacific/Honolulu",
        "AK": "America/Anchorage",
    },
    "GB": "Europe/London",
    "CA": "America/Toronto",
    "AU": "Australia/Sydney",
    "DE": "Europe/Berlin",
    "FR": "Europe/Paris",
    "ES": "Europe/Madrid",
    "IT": "Europe/Rome",
    "NL": "Europe/Amsterdam",
    "PL": "Europe/Warsaw",
    "BR": "America/Sao_Paulo",
    "PT": "Europe/Lisbon",
    "RU": "Europe/Moscow",
    "JP": "Asia/Tokyo",
    "KR": "Asia/Seoul",
    "CN": "Asia/Shanghai",
    "TW": "Asia/Taipei",
    "IN": "Asia/Kolkata",
    "ID": "Asia/Jakarta",
    "TH": "Asia/Bangkok",
    "VN": "Asia/Ho_Chi_Minh",
    "TR": "Europe/Istanbul",
    "SA": "Asia/Riyadh",
    "AE": "Asia/Dubai",
    "EG": "Africa/Cairo",
    "MX": "America/Mexico_City",
    "AR": "America/Argentina/Buenos_Aires",
    "CL": "America/Santiago",
    "CO": "America/Bogota",
    "NG": "Africa/Lagos",
    "ZA": "Africa/Johannesburg",
    "KE": "Africa/Nairobi",
    "NZ": "Pacific/Auckland",
    "SG": "Asia/Singapore",
    "MY": "Asia/Kuala_Lumpur",
    "PH": "Asia/Manila",
    "PK": "Asia/Karachi",
    "BD": "Asia/Dhaka",
    "IR": "Asia/Tehran",
    "IL": "Asia/Jerusalem",
    "RO": "Europe/Bucharest",
    "HU": "Europe/Budapest",
    "CZ": "Europe/Prague",
    "GR": "Europe/Athens",
    "SE": "Europe/Stockholm",
    "NO": "Europe/Oslo",
    "DK": "Europe/Copenhagen",
    "FI": "Europe/Helsinki",
    "AT": "Europe/Vienna",
    "CH": "Europe/Zurich",
    "BE": "Europe/Brussels",
    "IE": "Europe/Dublin",
    "UA": "Europe/Kiev",
}


async def get_public_ip(proxy_server: Optional[str] = None) -> Optional[str]:
    """
    Get public IP address. If proxy_server is provided, use a proxy-aware check.
    Otherwise use direct connection.
    """
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=15)

    if proxy_server:
        proxy_url = proxy_server
        if not proxy_server.startswith("http"):
            proxy_url = f"http://{proxy_server}"

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    "https://api.ipify.org?format=json",
                    timeout=timeout,
                    proxy=proxy_url,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("ip")
        except Exception:
            pass

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    "https://ipinfo.io/json",
                    timeout=timeout,
                    proxy=proxy_url,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("ip")
        except Exception:
            pass

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    "https://ifconfig.me/ip",
                    timeout=timeout,
                    proxy=proxy_url,
                ) as resp:
                    if resp.status == 200:
                        return (await resp.text()).strip()
        except Exception:
            pass
    else:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.ipify.org?format=json", timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("ip")
        except Exception:
            pass

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://ipinfo.io/json", timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("ip")
        except Exception:
            pass

    return None


async def lookup_geolocation(ip_address: str) -> Optional[dict]:
    """
    Look up geolocation data for an IP address using free APIs.
    Returns timezone, country code, city, and locale info.
    """
    import aiohttp

    apis = [
        f"http://ip-api.com/json/{ip_address}?fields=status,country,countryCode,region,regionName,city,timezone,offset",
        f"https://ipinfo.io/{ip_address}/json",
    ]

    for api_url in apis:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()

                        if api_url.startswith("http://ip-api.com"):
                            if data.get("status") != "success":
                                continue
                            country_code = data.get("countryCode", "")
                            region_code = data.get("region", "")
                            city = data.get("city", "")
                            timezone_str = data.get("timezone", "")
                            offset = data.get("offset", 0)
                        else:
                            if data.get("bogon", False):
                                continue
                            country_code = data.get("country", "")
                            region_code = data.get("region", "")
                            city = data.get("city", "")
                            timezone_str = ""
                            loc = data.get("loc", "")
                            offset = 0

                            if loc:
                                lat, lon = loc.split(",")

                                tz_api = f"https://maps.googleapis.com/maps/api/timezone/json?location={lat},{lon}&timestamp=0"
                                try:
                                    async with session.get(
                                        tz_api, timeout=aiohttp.ClientTimeout(total=5)
                                    ) as tz_resp:
                                        if tz_resp.status == 200:
                                            tz_data = await tz_resp.json()
                                            timezone_str = tz_data.get("timeZoneId", "")
                                except:
                                    timezone_str = _guess_timezone(
                                        country_code, region_code
                                    )
                            else:
                                timezone_str = _guess_timezone(
                                    country_code, region_code
                                )

                        language_codes = LANGUAGE_MAP.get(country_code, ("en", "en-US"))
                        locale = _pick_locale_variant(
                            language_codes, country_code, city
                        )

                        return {
                            "country_code": country_code,
                            "region_code": region_code,
                            "city": city,
                            "timezone": timezone_str,
                            "language_code": language_codes[0],
                            "locale": locale,
                            "offset": offset,
                        }
        except Exception:
            continue

    return None


def _guess_timezone(country_code: str, region_code: str = "") -> str:
    """Guess timezone from country and region code."""
    if country_code in TIMEZONE_MAP:
        mapping = TIMEZONE_MAP[country_code]
        if isinstance(mapping, dict):
            return mapping.get(region_code, list(mapping.values())[0])
        return mapping
    return "UTC"


def _pick_locale_variant(language_codes: tuple, country_code: str, city: str) -> str:
    """Pick the best locale variant based on country."""
    base_lang = language_codes[0]
    locale = f"{base_lang}-{country_code}"
    common_locales = {
        "en-US",
        "en-GB",
        "en-CA",
        "en-AU",
        "es-ES",
        "es-MX",
        "es-AR",
        "pt-BR",
        "pt-PT",
        "zh-CN",
        "zh-TW",
        "de-DE",
        "de-AT",
        "de-CH",
        "fr-FR",
        "fr-CA",
    }
    if locale in common_locales:
        return locale
    return (
        language_codes[1] if len(language_codes) > 1 else f"{base_lang}-{country_code}"
    )


async def get_geoip_data(proxy_server: Optional[str] = None) -> Optional[dict]:
    """
    Get complete geoip data for the current connection.
    Fetches public IP and looks up geolocation.
    """
    ip = await get_public_ip(proxy_server)
    if not ip:
        return None

    geo = await lookup_geolocation(ip)
    if geo:
        geo["ip"] = ip

    return geo
