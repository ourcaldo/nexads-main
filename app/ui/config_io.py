"""
nexads/ui/config_io.py
Config file I/O and default config for the GUI.
"""

import json
import os


DEFAULT_CONFIG = {
    "proxy": {
        "type": "http",
        "credentials": "",
        "file": ""
    },
    "browser": {
        "headless_mode": "virtual",
        "disable_ublock": True,
        "random_activity": True,
        "activities": ["scroll", "hover", "click"],
        "auto_accept_cookies": True,
        "prevent_redirects": True
    },
    "delay": {
        "min_time": 3,
        "max_time": 10
    },
    "session": {
        "enabled": False,
        "count": 0,
        "max_time": 30
    },
    "threads": 5,
    "os_fingerprint": ["windows", "macos", "linux"],
    "device_type": {
        "mobile": 0,
        "desktop": 100
    },
    "referrer": {
        "types": ["random"],
        "organic_keywords": "example\nsearch terms\nkeywords"
    },
    "urls": [
        {
            "url": "https://example.com",
            "random_page": False,
            "min_time": 30,
            "max_time": 60
        }
    ],
    "ads": {
        "ctr": 5.0,
        "providers": ["adsense"],
        "strategy": "first_success",
        "min_time": 10,
        "max_time": 30
    }
}


def load_config(config_path: str) -> dict:
    """Load configuration from JSON file or return defaults."""
    import copy
    default = copy.deepcopy(DEFAULT_CONFIG)

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            for key, value in default.items():
                if key not in config:
                    config[key] = value
            # Backward compatibility for old referrer format
            if "type" in config["referrer"]:
                old_type = config["referrer"]["type"]
                if old_type == "random":
                    config["referrer"]["types"] = ["random"]
                else:
                    config["referrer"]["types"] = [old_type]
                del config["referrer"]["type"]
            return config
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Warning: Config file is invalid ({e}), falling back to defaults.")
            return default
    return default


def write_config(config_path: str, config: dict) -> bool:
    """Write config dict to JSON file. Returns True on success."""
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config file: {str(e)}")
        return False
