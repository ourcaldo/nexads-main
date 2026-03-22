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

from app.core.timings import timing_seconds

from datetime import datetime
from app.ads.signals import ensure_adsense_signals_updated

_PKG_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = _PKG_ROOT / "config.json"


class SessionFailedException(Exception):
    """Raised when a session cannot continue."""
    pass


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

    def start(self):
        """Start the nexAds automation with configured threads."""
        from app.core.worker import run_worker

        if self.running:
            print("Already running")
            return

        self.running = True
        self.start_time = datetime.now()

        # Rotate JSONL telemetry files at startup to prevent unbounded growth.
        self._rotate_telemetry_logs()

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
                stagger = timing_seconds("worker_stagger")
                print(f"Staggering next worker by {stagger:.0f}s...")
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

    def _rotate_telemetry_logs(self):
        """Truncate JSONL telemetry files at startup to prevent unbounded growth."""
        data_dir = _PKG_ROOT / "data"
        for filename in ("worker_events.jsonl", "worker_errors.jsonl",
                         "telemetry_mobile.jsonl", "ad_click_events.jsonl"):
            filepath = data_dir / filename
            if filepath.exists():
                try:
                    size_mb = filepath.stat().st_size / (1024 * 1024)
                    if size_mb > 10:
                        filepath.write_text("")
                        print(f"Rotated {filename} ({size_mb:.1f}MB -> 0)")
                except Exception:
                    pass

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
