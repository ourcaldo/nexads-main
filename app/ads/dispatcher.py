"""
nexads/ads/dispatcher.py
Multi-provider ad interaction dispatcher.
"""

import time

from app.ads.adsense import interact_with_ads as _adsense_interact
from app.ads.adsterra import interact_with_adsterra_ads as _adsterra_interact

_PROVIDER_HANDLERS = {
    "adsense": _adsense_interact,
    "adsterra": _adsterra_interact,
}


async def dispatch_ad_interaction(page, browser, worker_id: int, extract_domain_fn,
                                  config: dict, interaction_state: dict,
                                  max_duration: float = 0) -> bool:
    """Route ad interaction to providers based on config strategy.

    Returns True if a click was accepted in this call.
    """
    providers = config.get("ads", {}).get("providers", ["adsense"])
    strategy = config.get("ads", {}).get("strategy", "first_success")

    if not providers:
        return False

    start_time = time.time()

    if strategy == "one_per_provider":
        # Try each unsatisfied provider, sharing the time budget
        any_success = False
        for provider in providers:
            if interaction_state.get(f"ad_click_success_{provider}"):
                continue

            if max_duration > 0:
                elapsed = time.time() - start_time
                remaining = max_duration - elapsed
                if remaining <= 0:
                    break
            else:
                remaining = 0

            handler = _PROVIDER_HANDLERS.get(provider)
            if not handler:
                continue

            print(f"Worker {worker_id}: Trying {provider} ads (one_per_provider)")
            success = await handler(
                page, browser, worker_id, extract_domain_fn,
                max_duration=remaining,
            )
            if success:
                interaction_state[f"ad_click_success_{provider}"] = True
                any_success = True
                # Mark session goal met only when ALL providers satisfied
                if all(interaction_state.get(f"ad_click_success_{p}") for p in providers):
                    interaction_state["ad_click_success"] = True

        return any_success

    # first_success: try providers in config order, share time budget
    for provider in providers:
        if max_duration > 0:
            elapsed = time.time() - start_time
            remaining = max_duration - elapsed
            if remaining <= 0:
                break
        else:
            remaining = 0

        handler = _PROVIDER_HANDLERS.get(provider)
        if not handler:
            continue

        print(f"Worker {worker_id}: Trying {provider} ads (first_success)")
        success = await handler(
            page, browser, worker_id, extract_domain_fn,
            max_duration=remaining,
        )
        if success:
            interaction_state["ad_click_success"] = True
            interaction_state["ad_click_provider"] = provider
            return True

    return False
