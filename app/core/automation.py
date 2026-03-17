"""
nexads/core/automation.py
Core nexAds class: config loading, session distribution, worker orchestration.
"""

import sys
import json
import random
import time
import multiprocessing
import pathlib

from datetime import datetime

_PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = _PKG_ROOT / "config.json"


class SessionFailedException(Exception):
    """Raised when a session cannot continue."""
    pass


class RateLimiter:
    """Async-compatible rate limiter capped at max_calls_per_minute."""

    def __init__(self, max_calls_per_minute: int = 300):
        import asyncio
        self.max_calls = max_calls_per_minute
        self.calls = []
        self.lock = asyncio.Lock()

    async def wait_if_needed(self):
        import asyncio
        import time as _time
        async with self.lock:
            now = _time.time()
            self.calls = [t for t in self.calls if now - t < 60]
            if len(self.calls) >= self.max_calls:
                oldest_call = self.calls[0]
                wait_time = 60 - (now - oldest_call)
                if wait_time > 0:
                    print(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                    await asyncio.sleep(wait_time)
            self.calls.append(_time.time())


class nexAds:
    """Main nexAds automation controller."""

    def __init__(self, config_path=None):
        self.config_path = str(config_path or CONFIG_PATH)
        self.load_config()
        self.workers = []
        self.running = False
        self.session_counts = {}
        self.successful_sessions = {}
        self.ads_session_counts = {}
        self.successful_ads_sessions = {}
        self.start_time = None
        self.total_sessions = 0
        self.ads_sessions = 0
        self.calculate_session_distribution()
        self.failed_ads_sessions = 0
        self.pending_ads_sessions = 0
        self._ad_click_success = {}
        self.lock = multiprocessing.Lock()
        self.manager = multiprocessing.Manager()
        self.rate_limiter = RateLimiter()

    def load_config(self):
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            if "type" in self.config["referrer"]:
                old_type = self.config["referrer"]["type"]
                if old_type == "random":
                    self.config["referrer"]["types"] = ["random"]
                else:
                    self.config["referrer"]["types"] = [old_type]
                del self.config["referrer"]["type"]
            if self.config['proxy']['credentials'] and self.config['proxy']['file']:
                print("Warning: Both proxy credentials and file are specified. "
                      "Using credentials and ignoring file.")
                self.config['proxy']['file'] = ""
        except FileNotFoundError:
            print(f"Config file {self.config_path} not found. "
                  "Please create one using the --config option.")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"Invalid config file {self.config_path}. "
                  "Please check the file or create a new one with --config.")
            sys.exit(1)

    def calculate_session_distribution(self):
        """Calculate how many sessions should include ad interactions based on CTR."""
        if not self.config['session']['enabled'] or self.config['session']['count'] == 0:
            threads = self.config['threads']
            max_time_min = self.config['session']['max_time']
            if max_time_min > 0:
                sessions_per_hour_per_thread = 60 / max_time_min
                self.total_sessions = int(threads * sessions_per_hour_per_thread)
            else:
                self.total_sessions = 100
        else:
            self.total_sessions = self.config['threads'] * self.config['session']['count']

        self.ads_sessions = max(1, int(self.total_sessions * (self.config['ads']['ctr'] / 100)))
        self.pending_ads_sessions = self.ads_sessions
        self.ads_session_flags = [False] * self.total_sessions
        for i in random.sample(range(self.total_sessions),
                               min(self.ads_sessions, self.total_sessions)):
            self.ads_session_flags[i] = True

    def get_random_delay(self, min_time=None, max_time=None) -> int:
        """Generate a random delay between min and max time."""
        min_val = min_time if min_time is not None else self.config['delay']['min_time']
        max_val = max_time if max_time is not None else self.config['delay']['max_time']
        return random.randint(min_val, max_val)

    def start(self):
        """Start the nexAds automation with configured threads."""
        from app.core.worker import run_worker

        if self.running:
            print("Already running")
            return

        self.running = True
        self.start_time = datetime.now()
        self.session_counts = {}
        self.successful_sessions = {}
        self.ads_session_counts = {}
        self.successful_ads_sessions = {}
        self.failed_ads_sessions = 0

        print(f"Starting nexAds with {self.config['threads']} threads")
        print(f"Total sessions planned: {self.total_sessions} (Ads: {self.ads_sessions})")

        self.workers = []

        for i in range(self.config['threads']):
            p = multiprocessing.Process(
                target=run_worker,
                args=(self.config_path, i + 1,
                      self.ads_session_flags, self.pending_ads_sessions)
            )
            p.start()
            self.workers.append(p)

        try:
            while any(p.is_alive() for p in self.workers):
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

        print("\nAll workers completed")

        total_sessions = sum(self.session_counts.values())
        successful_sessions = sum(self.successful_sessions.values())
        total_ads_sessions = sum(self.ads_session_counts.values())
        successful_ads_sessions = sum(self.successful_ads_sessions.values())

        print(f"Total sessions attempted: {total_sessions}")
        print(f"Successful sessions: {successful_sessions} "
              f"({successful_sessions / max(1, total_sessions) * 100:.1f}%)")
        print(f"Total ads sessions attempted: {total_ads_sessions}")
        print(f"Successful ads sessions: {successful_ads_sessions} "
              f"({successful_ads_sessions / max(1, total_ads_sessions) * 100:.1f}%)")
        print(f"Failed ads sessions: {self.failed_ads_sessions}")
        print(f"Actual CTR: "
              f"{successful_ads_sessions / max(1, successful_sessions) * 100:.2f}% "
              f"(Target: {self.config['ads']['ctr']}%)")

    def stop(self):
        """Stop the nexAds automation and terminate all workers."""
        if not self.running:
            return

        self.running = False
        print("Stopping all workers...")

        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=10)

        runtime = datetime.now() - self.start_time
        print(f"nexAds stopped. Total runtime: {runtime}")
