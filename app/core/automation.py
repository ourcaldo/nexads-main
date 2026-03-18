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
from app.ads.signals import ensure_adsense_signals_updated

_PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = _PKG_ROOT / "config.json"


class SessionFailedException(Exception):
    """Raised when a session cannot continue."""
    pass


class RateLimiter:
    """Async-compatible rate limiter capped at max_calls_per_minute."""

    def __init__(self, max_calls_per_minute: int = 300):
        self.max_calls = max_calls_per_minute
        self.calls = []
        self._lock = None  # created lazily inside the event loop

    def _get_lock(self):
        import asyncio
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def wait_if_needed(self):
        import asyncio
        import time as _time
        async with self._get_lock():
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
        self.start_time = None
        self.total_sessions = 0
        self.ads_sessions = 0
        self.calculate_session_distribution()
        self.manager = None
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
        session_enabled = self.config['session']['enabled']
        session_count = self.config['session']['count']
        threads = self.config['threads']

        if session_enabled and session_count > 0:
            # Finite session mode: count is explicit
            self.total_sessions = threads * session_count
        else:
            # session.count == 0 means unlimited sessions.
            self.total_sessions = 0  # 0 = unlimited; ads_sessions used as rolling budget

        if self.total_sessions > 0:
            self.ads_sessions = max(1, int(self.total_sessions * (self.config['ads']['ctr'] / 100)))
        else:
            # Unlimited: start with a generous budget; workers will run indefinitely
            self.ads_sessions = max(1, int(100 * (self.config['ads']['ctr'] / 100)))

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

        # Refresh AdSense signal cache once in the parent process before workers spawn.
        try:
            updated, message = ensure_adsense_signals_updated()
            prefix = "updated" if updated else "cached"
            print(f"AdSense signals {prefix}: {message}")
        except Exception as e:
            print(f"Warning: could not refresh AdSense signals: {str(e)}")

        # Create shared state via Manager so workers can write back stats
        self.manager = multiprocessing.Manager()
        shared = {
            'pending_ads_sessions': self.manager.Value('i', self.ads_sessions),
            'session_counts': self.manager.dict(),
            'successful_sessions': self.manager.dict(),
            'ads_session_counts': self.manager.dict(),
            'successful_ads_sessions': self.manager.dict(),
        }

        print(f"Starting nexAds with {self.config['threads']} threads")
        print(f"Total sessions planned: {self.total_sessions} (Ads: {self.ads_sessions})")

        self.workers = []

        for i in range(self.config['threads']):
            worker_id = i + 1
            # Initialize per-worker counters in shared dicts
            shared['session_counts'][worker_id] = 0
            shared['successful_sessions'][worker_id] = 0
            shared['ads_session_counts'][worker_id] = 0
            shared['successful_ads_sessions'][worker_id] = 0

            p = multiprocessing.Process(
                target=run_worker,
                args=(self.config_path, worker_id,
                      shared['pending_ads_sessions'],
                      shared['session_counts'],
                      shared['successful_sessions'],
                      shared['ads_session_counts'],
                      shared['successful_ads_sessions'])
            )
            p.start()
            self.workers.append(p)
            # Stagger worker startups — avoids simultaneous proxy connections
            # and looks more natural; skip delay after the last worker
            if i < self.config['threads'] - 1:
                stagger = random.randint(2, 5)
                print(f"Staggering next worker by {stagger}s...")
                time.sleep(stagger)

        try:
            while any(p.is_alive() for p in self.workers):
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

        print("\nAll workers completed")

        total_sessions = sum(shared['session_counts'].values())
        successful_sessions = sum(shared['successful_sessions'].values())
        total_ads_sessions = sum(shared['ads_session_counts'].values())
        successful_ads_sessions = sum(shared['successful_ads_sessions'].values())

        print(f"Total sessions attempted: {total_sessions}")
        print(f"Successful sessions: {successful_sessions} "
              f"({successful_sessions / max(1, total_sessions) * 100:.1f}%)")
        print(f"Total ads sessions attempted: {total_ads_sessions}")
        print(f"Successful ads sessions: {successful_ads_sessions} "
              f"({successful_ads_sessions / max(1, total_ads_sessions) * 100:.1f}%)")
        print(f"Actual CTR: "
              f"{successful_ads_sessions / max(1, successful_sessions) * 100:.2f}% "
              f"(Target: {self.config['ads']['ctr']}%)")

        self._shutdown_manager()

    def _shutdown_manager(self):
        """Shut down the multiprocessing Manager server process."""
        if self.manager:
            try:
                self.manager.shutdown()
            except Exception:
                pass
            self.manager = None

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

        self._shutdown_manager()

        if self.start_time:
            runtime = datetime.now() - self.start_time
            print(f"nexAds stopped. Total runtime: {runtime}")
        else:
            print("nexAds stopped.")
