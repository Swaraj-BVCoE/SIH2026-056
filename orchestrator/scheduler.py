"""
orchestrator/scheduler.py
──────────────────────────
APScheduler-based cron daemon for automated periodic scraping.

Runs the full scrape pipeline on the configured SCRAPE_CRON schedule.
Also supports one-shot triggering via trigger_now().
"""

from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from config.settings import settings
from orchestrator.job_runner import run_all, select_scheduled_routes


class ScrapeScheduler:
    """
    Manages the APScheduler cron job for periodic scraping.

    Usage:
        scheduler = ScrapeScheduler()
        scheduler.start()   # blocks until Ctrl+C
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
        self._is_running = False

    def configure(self) -> None:
        """Register the scrape job with the scheduler."""
        trigger = CronTrigger.from_crontab(
            settings.scrape_cron,
            timezone="Asia/Kolkata",
        )
        self._scheduler.add_job(
            func=self._run_scrape_cycle,
            trigger=trigger,
            id="full_scrape",
            name="Full Airfare Scrape",
            replace_existing=True,
            max_instances=1,  # Prevent overlap
            coalesce=True,    # If missed, run once (not multiple times)
        )
        logger.info(
            "Scrape job scheduled: {} (Asia/Kolkata)",
            settings.scrape_cron,
        )

    async def _run_scrape_cycle(self) -> None:
        """Called by the scheduler on each trigger."""
        start = datetime.now(tz=timezone.utc)
        logger.info("=" * 60)
        logger.info("SCHEDULED SCRAPE STARTING: {}", start.isoformat())
        logger.info("=" * 60)

        try:
            routes = select_scheduled_routes()
            logger.info(
                "Scheduled route batch: {}",
                ", ".join(route.code for route in routes),
            )
            results = await run_all(routes=routes)
            total = sum(r.get("records", 0) for r in results if isinstance(r, dict))
            logger.success(
                "SCHEDULED SCRAPE COMPLETE: {} records saved in {:.1f}s",
                total,
                (datetime.now(tz=timezone.utc) - start).total_seconds(),
            )
        except Exception as exc:
            logger.exception("SCHEDULED SCRAPE FAILED: {}", exc)

    def start(self) -> None:
        """Start the scheduler and block until SIGINT/SIGTERM."""
        self.configure()
        self._scheduler.start()
        self._is_running = True

        logger.info("Scheduler started. Press Ctrl+C to stop.")
        logger.info("Next run: {}", self._scheduler.get_job("full_scrape").next_run_time)

        # Register shutdown handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown)
            except (NotImplementedError, RuntimeError):
                # Windows doesn't support add_signal_handler for all signals
                pass

        try:
            loop.run_forever()
        except (KeyboardInterrupt, SystemExit):
            self._shutdown()

    def _shutdown(self) -> None:
        if self._is_running:
            logger.info("Shutting down scheduler...")
            self._scheduler.shutdown(wait=False)
            self._is_running = False
            asyncio.get_event_loop().stop()

    async def trigger_now(self) -> list[dict]:
        """Manually trigger a full scrape cycle immediately."""
        logger.info("Manual trigger: starting full scrape cycle now")
        return await run_all()

    def next_run(self) -> str | None:
        """Return the next scheduled run time as a string."""
        job = self._scheduler.get_job("full_scrape")
        if job and job.next_run_time:
            return str(job.next_run_time)
        return None
