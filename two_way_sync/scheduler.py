"""Background scheduler for incremental sync, retry worker, and reconciliation."""

import asyncio
import contextlib
import os

from two_way_sync.sync_logic import SyncService
from two_way_sync.utils.logger import log_error, log_info

INCREMENTAL_SECONDS = int(os.getenv("INCREMENTAL_SYNC_SECONDS", "900"))
RETRY_SECONDS = int(os.getenv("RETRY_WORKER_SECONDS", "180"))
RECONCILE_SECONDS = int(os.getenv("RECONCILE_SECONDS", "3600"))


class SyncScheduler:
    """Runs background sync jobs while the FastAPI app is alive."""

    def __init__(self):
        """Initialize task tracking and a shared shutdown event."""
        self._tasks = []
        self._stop_event = asyncio.Event()

    def start(self):
        """Start incremental, retry, and reconciliation loops."""
        self._tasks = [
            asyncio.create_task(self._run_on_startup_incremental()),
            asyncio.create_task(self._loop("incremental", INCREMENTAL_SECONDS, self._incremental)),
            asyncio.create_task(self._loop("retry", RETRY_SECONDS, self._retry)),
            asyncio.create_task(self._loop("reconciliation", RECONCILE_SECONDS, self._reconcile)),
        ]
        log_info("Scheduler started")

    async def stop(self):
        """Cancel running scheduler tasks during application shutdown."""
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        log_info("Scheduler stopped")

    async def _run_on_startup_incremental(self):
        """Run one catch-up sync immediately after service startup."""
        try:
            await asyncio.to_thread(self._incremental)
        except Exception as exc:
            log_error(f"Startup incremental sync failed: {exc}")

    async def _loop(self, name, interval_seconds, job):
        """Run a blocking sync job repeatedly without blocking the event loop."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                try:
                    await asyncio.to_thread(job)
                except Exception as exc:
                    log_error(f"Scheduled {name} job failed: {exc}")

    def _incremental(self):
        """Run incremental catch-up work."""
        SyncService().run_incremental_sync()

    def _retry(self):
        """Retry failed API operations."""
        SyncService().retry_due_items()

    def _reconcile(self):
        """Run scheduled drift reconciliation."""
        SyncService().run_reconciliation()
