from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import median

from sqlalchemy import func
from sqlalchemy.orm import Session

from config.routes import ROUTE_BASKET
from config.settings import settings
from db.models import FlightPrice, ScrapeRun
from index.calculator import calculate_index_series, percentage_change, value_on_or_before
from index.weights import load_weights

CONFIGURED_SOURCES = [
    "indigo_direct", "air_india_direct", "akasa_direct", "spicejet_direct",
    "makemytrip", "cleartrip", "ixigo", "easemytrip",
]
LEAD_WINDOWS = [1, 7, 15, 30, 45]


def classify_advance_window(days: int) -> int | None:
    if days < 0 or days > 60:
        return None
    if days <= 3:
        return 1
    if days <= 11:
        return 7
    if days <= 22:
        return 15
    if days <= 37:
        return 30
    return 45


def freshness_payload(latest: datetime | None) -> dict:
    if latest is None:
        return {"status": "NO DATA", "last_updated": None, "age_hours": None}
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    age = max(0, (datetime.now(timezone.utc) - latest).total_seconds() / 3600)
    status = "FRESH" if age < settings.freshness_fresh_hours else "DELAYED" if age < settings.freshness_delayed_hours else "STALE"
    return {"status": status, "last_updated": latest.isoformat(), "age_hours": round(age, 1)}


def daily_route_rows(db: Session) -> list[dict]:
    rows = db.query(
        func.date(FlightPrice.scraped_at).label("observed_date"),
        FlightPrice.origin,
        FlightPrice.destination,
        func.avg(FlightPrice.total_fare).label("avg_fare"),
        func.count(FlightPrice.id).label("count"),
    ).filter(FlightPrice.is_outlier.is_(False)).group_by(
        func.date(FlightPrice.scraped_at), FlightPrice.origin, FlightPrice.destination
    ).order_by(func.date(FlightPrice.scraped_at)).all()
    return [{
        "date": date.fromisoformat(str(row.observed_date)),
        "route": f"{row.origin}-{row.destination}",
        "avg_fare": float(row.avg_fare),
        "count": row.count,
    } for row in rows]


def index_context(db: Session) -> tuple[list[dict], dict]:
    rows = daily_route_rows(db)
    observed_routes = {row["route"] for row in rows}
    weights, metadata = load_weights(settings.index_weights_file, observed_routes)
    metadata["base_period"] = settings.index_base_period
    return calculate_index_series(rows, weights), metadata


def route_period_metrics(db: Session, days: int = 7) -> list[dict]:
    latest = db.query(func.max(FlightPrice.scraped_at)).scalar()
    if latest is None:
        return []
    current_start = latest - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)
    rows = db.query(FlightPrice).filter(
        FlightPrice.is_outlier.is_(False), FlightPrice.scraped_at >= previous_start
    ).all()
    grouped: dict[str, dict[str, list[FlightPrice]]] = defaultdict(lambda: {"current": [], "previous": []})
    for row in rows:
        key = f"{row.origin}-{row.destination}"
        grouped[key]["current" if row.scraped_at >= current_start else "previous"].append(row)
    result = []
    basket_size = max(len(ROUTE_BASKET), 1)
    for route, periods in grouped.items():
        current = periods["current"]
        previous = periods["previous"]
        if not current:
            continue
        current_avg = sum(r.total_fare for r in current) / len(current)
        previous_avg = sum(r.total_fare for r in previous) / len(previous) if previous else None
        change = percentage_change(current_avg, previous_avg)
        sources = {r.source_portal for r in current}
        result.append({
            "route": route,
            "origin": route[:3],
            "destination": route[-3:],
            "current_avg_fare": round(current_avg, 2),
            "previous_avg_fare": round(previous_avg, 2) if previous_avg is not None else None,
            "change_percent": change,
            "weighted_contribution": round((change or 0) / basket_size, 3) if change is not None else None,
            "observations": len(current),
            "source_coverage": len(sources),
        })
    return sorted(result, key=lambda item: item["change_percent"] if item["change_percent"] is not None else -999, reverse=True)


def source_statuses(db: Session) -> list[dict]:
    latest_fare = db.query(func.max(FlightPrice.scraped_at)).scalar()
    statuses = []
    for source in CONFIGURED_SOURCES:
        runs = db.query(ScrapeRun).filter(ScrapeRun.source_portal == source).order_by(ScrapeRun.started_at.desc()).limit(100).all()
        records = db.query(func.count(FlightPrice.id)).filter(FlightPrice.source_portal == source).scalar() or 0
        routes = db.query(func.count(func.distinct(FlightPrice.origin + FlightPrice.destination))).filter(FlightPrice.source_portal == source).scalar() or 0
        last_success = db.query(func.max(ScrapeRun.finished_at)).filter(ScrapeRun.source_portal == source, ScrapeRun.status == "SUCCESS").scalar()
        successes = sum(run.status == "SUCCESS" for run in runs)
        terminal = [run for run in runs if run.status != "RUNNING"]
        rate = successes / len(terminal) * 100 if terminal else None
        latest_status = runs[0].status if runs else "NO DATA"
        if latest_status == "BLOCKED":
            status = "BLOCKED"
        elif not runs and records == 0:
            status = "NO DATA"
        elif rate is not None and rate >= 80:
            status = "HEALTHY"
        elif records or runs:
            status = "PARTIAL"
        else:
            status = "OFFLINE"
        statuses.append({
            "source": source, "status": status, "success_rate": round(rate, 1) if rate is not None else None,
            "last_successful_collection": last_success.isoformat() if last_success else None,
            "records": records, "routes_covered": routes,
        })
    return statuses


def lead_time_rows(db: Session, origin=None, destination=None, airline=None, source=None) -> list[dict]:
    query = db.query(FlightPrice).filter(FlightPrice.is_outlier.is_(False))
    for column, value in ((FlightPrice.origin, origin), (FlightPrice.destination, destination), (FlightPrice.airline, airline), (FlightPrice.source_portal, source)):
        if value:
            query = query.filter(column == value)
    buckets: dict[int, list[float]] = defaultdict(list)
    for row in query.all():
        bucket = classify_advance_window(row.advance_days)
        if bucket:
            buckets[bucket].append(row.total_fare)
    result = []
    for window in LEAD_WINDOWS:
        fares = buckets.get(window, [])
        result.append({"advance_days": window, "label": f"T+{window}", "average_fare": round(sum(fares) / len(fares), 2) if fares else None, "observations": len(fares)})
    return result
