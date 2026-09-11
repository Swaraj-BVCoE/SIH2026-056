"""Bounded, fair scraper orchestration with auditable terminal outcomes."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Type

from loguru import logger
from sqlalchemy import func

from config.routes import ROUTE_BASKET, Route
from config.settings import settings
from db.database import get_db
from db.models import ScrapeRun
from pipeline.normalizer import normalize_batch
from pipeline.storage import save_records
from pipeline.validator import validate_batch
from scraper import ALL_SCRAPERS
from scraper.base_scraper import BaseScraper, FareRecord
from scraper.browser import BrowserPool
from scraper.proxy import proxy_pool


def default_travel_dates(today: date | None = None) -> list[date]:
    """Return the configured CPI advance-purchase dates instead of all 60 days."""
    today = today or datetime.now(tz=timezone.utc).date()
    return [today + timedelta(days=days) for days in settings.lead_time_days]


def build_job_plan(
    scraper_classes: list[Type[BaseScraper]],
    routes: list[Route],
    travel_dates: list[date],
) -> list[tuple[Type[BaseScraper], Route, date]]:
    """Create a fair Cartesian plan.

    Each pass covers every route while rotating its first source. This means a
    safely interrupted run still improves route and source coverage instead of
    spending hours on one source/route/date prefix.
    """
    if not scraper_classes or not routes or not travel_dates:
        return []
    plan: list[tuple[Type[BaseScraper], Route, date]] = []
    source_count = len(scraper_classes)
    for travel_date in travel_dates:
        for source_pass in range(source_count):
            for route_index, route in enumerate(routes):
                scraper_class = scraper_classes[(route_index + source_pass) % source_count]
                plan.append((scraper_class, route, travel_date))
    return plan


def recover_stale_runs() -> int:
    """Close audit rows left RUNNING by a terminated process; never delete them."""
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(hours=settings.stale_run_hours)
    with get_db() as db:
        count = db.query(ScrapeRun).filter(
            ScrapeRun.status == "RUNNING", ScrapeRun.started_at < cutoff
        ).update(
            {
                ScrapeRun.status: "INTERRUPTED",
                ScrapeRun.finished_at: now,
                ScrapeRun.error_message: "Collection process ended before this queued/running job completed.",
            },
            synchronize_session=False,
        )
    if count:
        logger.warning("[runner] Recovered {} stale RUNNING audit rows as INTERRUPTED", count)
    return count


def select_scheduled_routes(limit: int | None = None) -> list[Route]:
    """Choose least-recently attempted routes so scheduled cycles rotate coverage."""
    limit = max(1, limit or settings.scheduled_routes_per_cycle)
    with get_db() as db:
        rows = db.query(
            ScrapeRun.origin,
            ScrapeRun.destination,
            func.max(ScrapeRun.started_at).label("last_attempt"),
        ).filter(ScrapeRun.status != "RUNNING").group_by(
            ScrapeRun.origin, ScrapeRun.destination
        ).all()
    last_attempt = {(row.origin, row.destination): row.last_attempt for row in rows}
    minimum = datetime.min
    ordered = sorted(
        ROUTE_BASKET,
        key=lambda route: (
            last_attempt.get((route.origin, route.destination), minimum),
            route.code,
        ),
    )
    return ordered[: min(limit, len(ordered))]


async def run_single_job(
    scraper: BaseScraper,
    pool: BrowserPool,
    route: Route,
    travel_date: date,
) -> dict:
    """Execute one source/route/date job and always leave a terminal audit row."""
    proxy = await proxy_pool.get_proxy()
    with get_db() as db:
        run = ScrapeRun(
            started_at=datetime.now(tz=timezone.utc),
            source_portal=scraper.SOURCE_PORTAL,
            origin=route.origin,
            destination=route.destination,
            travel_date=travel_date,
            status="RUNNING",
            proxy_used=proxy,
        )
        db.add(run)
        db.flush()
        run_id = run.id

    status = "FAILED"
    records_inserted = 0
    error_msg = ""
    invalid_count = 0
    try:
        async with pool.acquire_page(
            proxy_server=proxy, source_portal=scraper.SOURCE_PORTAL
        ) as page:
            raw_records: list[FareRecord] = await scraper.scrape(
                page, route, travel_date, scrape_run_id=run_id
            )

        if raw_records:
            normalized = normalize_batch(raw_records, scraper.SOURCE_PORTAL)
            validated, invalid_count = validate_batch(normalized)
            records_inserted = save_records(validated, scrape_run_id=run_id)
            status = "SUCCESS" if validated else "PARTIAL"
            if invalid_count:
                error_msg = f"{invalid_count} parsed records failed validation."
            if proxy:
                proxy_pool.mark_success(proxy)
        else:
            status = scraper.last_status if scraper.last_status != "RUNNING" else "NO_DATA"
            error_msg = scraper.last_error
            logger.info(
                "[runner] {} for {} {} ({})",
                status, route.code, travel_date, scraper.SOURCE_PORTAL,
            )
    except asyncio.CancelledError:
        status = "INTERRUPTED"
        error_msg = "Collection process was interrupted."
        raise
    except Exception as exc:
        error_msg = str(exc)
        status = "FAILED"
        logger.error(
            "[runner] Job FAILED: {} {} {} | {}",
            route.code, travel_date, scraper.SOURCE_PORTAL, exc,
        )
        if proxy:
            proxy_pool.mark_failure(proxy)
    finally:
        with get_db() as db:
            run = db.get(ScrapeRun, run_id)
            if run:
                run.finished_at = datetime.now(tz=timezone.utc)
                run.status = status
                run.records_inserted = records_inserted
                run.error_message = error_msg or None

    return {
        "portal": scraper.SOURCE_PORTAL,
        "route": route.code,
        "travel_date": str(travel_date),
        "status": status,
        "records": records_inserted,
        "invalid_records": invalid_count,
        "error": error_msg or None,
    }


async def run_all(
    scraper_classes: list[Type[BaseScraper]] | None = None,
    routes: list[Route] | None = None,
    travel_dates: list[date] | None = None,
    max_jobs: int | None = None,
) -> list[dict]:
    """Run a bounded worker queue without pre-creating database audit rows."""
    scraper_classes = scraper_classes or ALL_SCRAPERS
    routes = routes or ROUTE_BASKET
    travel_dates = travel_dates or default_travel_dates()
    recover_stale_runs()

    plan = build_job_plan(scraper_classes, routes, travel_dates)
    if max_jobs is not None:
        plan = plan[:max(0, max_jobs)]
    logger.info(
        "[runner] Starting {} jobs ({} sources × {} routes × {} lead-time dates)",
        len(plan), len(scraper_classes), len(routes), len(travel_dates),
    )

    queue: asyncio.Queue = asyncio.Queue()
    for job in plan:
        queue.put_nowait(job)
    results: list[dict] = []

    async with BrowserPool() as pool:
        async def worker() -> None:
            while True:
                try:
                    scraper_class, route, travel_date = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    result = await run_single_job(scraper_class(), pool, route, travel_date)
                    results.append(result)
                finally:
                    queue.task_done()

        worker_count = min(max(1, settings.max_concurrent_scrapers), len(plan))
        workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
        try:
            await asyncio.gather(*workers)
        except BaseException:
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            raise

    terminal_success = sum(r["status"] == "SUCCESS" for r in results)
    total_records = sum(r["records"] for r in results)
    logger.success(
        "[runner] Done: {} successful, {} no-data, {} blocked/offline/failed | {} records saved",
        terminal_success,
        sum(r["status"] == "NO_DATA" for r in results),
        sum(r["status"] not in {"SUCCESS", "NO_DATA"} for r in results),
        total_records,
    )
    return results


async def run_route(
    route_code: str,
    travel_date: date | list[date] | None = None,
    scraper_classes: list[Type[BaseScraper]] | None = None,
) -> list[dict]:
    from config.routes import get_route

    dates = travel_date if isinstance(travel_date, list) else [travel_date] if travel_date else default_travel_dates()
    return await run_all(
        scraper_classes=scraper_classes,
        routes=[get_route(route_code)],
        travel_dates=dates,
    )
