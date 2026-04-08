"""
nexads/core/worker.py
Worker entry points and shared context dataclass.
Session logic lives in app/core/session.py (SessionRunner).
"""

import asyncio
import os
import psutil
from dataclasses import dataclass

from app.core.session import SessionRunner


@dataclass
class WorkerContext:
    """Shared state passed to every worker function."""

    config: dict
    running: bool
    session_counts: object  # multiprocessing.Manager dict proxy
    successful_sessions: object  # multiprocessing.Manager dict proxy
    ads_session_counts: object  # multiprocessing.Manager dict proxy
    successful_ads_sessions: object  # multiprocessing.Manager dict proxy
    global_session_count: object  # multiprocessing.Manager Value proxy
    global_session_lock: object  # multiprocessing.Manager Lock proxy


def _kill_child_browser_processes(worker_id: int):
    """Kill orphaned browser processes (camoufox/chromium) that are children of this worker."""
    killed = 0
    try:
        parent = psutil.Process(os.getpid())
        for child in parent.children(recursive=True):
            try:
                child.kill()
                killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    if killed:
        print(f"Worker {worker_id}: Force-killed {killed} orphaned browser process(es)")


async def run_worker_async(
    config_path: str,
    worker_id: int,
    session_counts,
    successful_sessions,
    ads_session_counts,
    successful_ads_sessions,
    global_session_count,
    global_session_lock,
):
    """Top-level async entry point for a multiprocessing worker."""
    import json

    try:
        with open(config_path, "r") as f:
            config = json.load(f)

        ctx = WorkerContext(
            config=config,
            running=True,
            session_counts=session_counts,
            successful_sessions=successful_sessions,
            ads_session_counts=ads_session_counts,
            successful_ads_sessions=successful_ads_sessions,
            global_session_count=global_session_count,
            global_session_lock=global_session_lock,
        )
        runner = SessionRunner(ctx, worker_id, _kill_child_browser_processes)
        await runner.run()
    except Exception as e:
        print(f"Worker {worker_id}: Fatal error: {str(e)}")


def run_worker(
    config_path: str,
    worker_id: int,
    session_counts,
    successful_sessions,
    ads_session_counts,
    successful_ads_sessions,
    global_session_count,
    global_session_lock,
):
    """Wrapper to run async worker in a fresh event loop (called by multiprocessing)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(
        run_worker_async(
            config_path,
            worker_id,
            session_counts,
            successful_sessions,
            ads_session_counts,
            successful_ads_sessions,
            global_session_count,
            global_session_lock,
        )
    )
    loop.close()
