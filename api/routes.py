from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta
from statistics import median
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from api.analytics import CONFIGURED_SOURCES, LEAD_WINDOWS, freshness_payload, index_context, lead_time_rows, route_period_metrics, source_statuses
from api.schemas import IndexLatestResponse
from config.routes import AIRPORTS, ROUTE_BASKET
from config.settings import settings
from db.database import get_db_session
from db.models import FlightPrice, ScrapeRun
from index.calculator import aggregate_frequency, percentage_change, value_on_or_before
from index.methodology import METHODOLOGY

router = APIRouter()


def _apply_filters(query, origin=None, destination=None, airline=None, source=None, travel_date=None, scraped_date=None, advance_window=None, outlier=None):
    for column, value in ((FlightPrice.origin, origin), (FlightPrice.destination, destination), (FlightPrice.airline, airline), (FlightPrice.source_portal, source)):
        if value:
            query = query.filter(column == value)
    if travel_date:
        query = query.filter(FlightPrice.travel_date == travel_date)
    if scraped_date:
        query = query.filter(func.date(FlightPrice.scraped_at) == scraped_date)
    if advance_window in LEAD_WINDOWS:
        low, high = {1: (0, 3), 7: (4, 11), 15: (12, 22), 30: (23, 37), 45: (38, 60)}[advance_window]
        query = query.filter(FlightPrice.advance_days.between(low, high))
    if outlier is not None:
        query = query.filter(FlightPrice.is_outlier.is_(outlier))
    return query


def _fare_dict(row: FlightPrice) -> dict:
    return {"id": row.id, "scraped_at": row.scraped_at.isoformat(), "origin": row.origin, "destination": row.destination,
            "route": f"{row.origin}-{row.destination}", "travel_date": row.travel_date.isoformat(), "advance_days": row.advance_days,
            "airline": row.airline, "flight_number": row.flight_number, "source": row.source_portal, "base_fare": row.base_fare,
            "taxes": row.taxes_fees, "user_development_fee": None, "convenience_charges": None, "other_charges": None,
            "total_fare": row.total_fare, "fare_breakdown_available": row.base_fare is not None or row.taxes_fees is not None,
            "is_outlier": row.is_outlier}


@router.get("/index/latest", response_model=IndexLatestResponse, summary="Latest Airfare Price Index")
def latest_index(db: Session = Depends(get_db_session)):
    series, metadata = index_context(db)
    observed_at = db.query(func.max(FlightPrice.scraped_at)).scalar()
    if not series:
        return {"value": None, "daily_change": None, "weekly_change": None, "monthly_change": None, "base_period": metadata["base_period"],
                "last_updated": None, "routes_used": 0, "records_used": 0, "freshness": freshness_payload(None), "weights": metadata}
    latest = series[-1]
    return {"value": latest["value"],
            "daily_change": percentage_change(latest["value"], value_on_or_before(series, latest["date"] - timedelta(days=1))),
            "weekly_change": percentage_change(latest["value"], value_on_or_before(series, latest["date"] - timedelta(days=7))),
            "monthly_change": percentage_change(latest["value"], value_on_or_before(series, latest["date"] - timedelta(days=30))),
            "base_period": metadata["base_period"], "last_updated": observed_at.isoformat() if observed_at else None,
            "routes_used": latest["routes_used"], "records_used": latest["records_used"], "freshness": freshness_payload(observed_at), "weights": metadata}


@router.get("/index/trend", summary="Index time series")
def index_trend(frequency: Literal["daily", "weekly", "monthly"] = "daily", days: int = Query(30, ge=1, le=730), db: Session = Depends(get_db_session)):
    series, metadata = index_context(db)
    if series:
        cutoff = series[-1]["date"] - timedelta(days=days - 1)
        series = [item for item in series if item["date"] >= cutoff]
    values = aggregate_frequency(series, frequency)
    return {"frequency": frequency, "base_period": metadata["base_period"], "weights": metadata,
            "items": [{**item, "date": item["date"].isoformat()} for item in values]}


@router.get("/index/routes", summary="Route price relatives")
def index_routes(period: Literal["daily", "weekly", "monthly"] = "weekly", db: Session = Depends(get_db_session)):
    return {"period": period, "items": route_period_metrics(db, {"daily": 1, "weekly": 7, "monthly": 30}[period])}


@router.get("/index/contributions", summary="Inflation contributors and declines")
def contributions(period: Literal["daily", "weekly", "monthly"] = "weekly", db: Session = Depends(get_db_session)):
    measured = [row for row in route_period_metrics(db, {"daily": 1, "weekly": 7, "monthly": 30}[period]) if row["change_percent"] is not None]
    return {"period": period, "contributors": [r for r in measured if r["change_percent"] > 0][:5],
            "declines": sorted([r for r in measured if r["change_percent"] < 0], key=lambda r: r["change_percent"])[:5]}


@router.get("/overview", summary="Executive national snapshot")
def overview(db: Session = Depends(get_db_session)):
    latest = latest_index(db)
    sources = source_statuses(db)
    return {"index": latest, "routes_monitored": db.query(func.count(func.distinct(FlightPrice.origin + FlightPrice.destination))).scalar() or 0,
            "routes_configured": len(ROUTE_BASKET), "data_points": db.query(func.count(FlightPrice.id)).scalar() or 0,
            "sources_active": sum(item["status"] in {"HEALTHY", "PARTIAL"} for item in sources), "sources_configured": len(CONFIGURED_SOURCES)}


@router.get("/routes", summary="Configured route basket and coverage")
def routes_list(db: Session = Depends(get_db_session)):
    counts = {(r.origin, r.destination): r.count for r in db.query(FlightPrice.origin, FlightPrice.destination, func.count(FlightPrice.id).label("count")).group_by(FlightPrice.origin, FlightPrice.destination).all()}
    return [{"route": route.code, "origin": route.origin, "destination": route.destination, "origin_name": AIRPORTS.get(route.origin),
             "destination_name": AIRPORTS.get(route.destination), "observations": counts.get((route.origin, route.destination), 0)} for route in ROUTE_BASKET]


def _group_average(rows, attribute):
    groups = {}
    for row in rows:
        groups.setdefault(getattr(row, attribute), []).append(row.total_fare)
    return [{"name": key, "average_fare": round(sum(values) / len(values), 2), "observations": len(values)} for key, values in groups.items()]


@router.get("/routes/{origin}/{destination}", summary="Detailed route analytics")
def route_detail(origin: str, destination: str, db: Session = Depends(get_db_session)):
    origin, destination = origin.upper(), destination.upper()
    rows = db.query(FlightPrice).filter(FlightPrice.origin == origin, FlightPrice.destination == destination, FlightPrice.is_outlier.is_(False)).order_by(FlightPrice.scraped_at).all()
    if not rows:
        return {"route": f"{origin}-{destination}", "observations": 0, "message": "No observations available for this route and date range."}
    fares = [row.total_fare for row in rows]
    trend_groups = {}
    for row in rows:
        trend_groups.setdefault(row.scraped_at.date().isoformat(), []).append(row.total_fare)
    route_change = next((item["change_percent"] for item in route_period_metrics(db, 7) if item["route"] == f"{origin}-{destination}"), None)
    return {"route": f"{origin}-{destination}", "average_fare": round(sum(fares) / len(fares), 2), "minimum_fare": min(fares),
            "maximum_fare": max(fares), "median_fare": round(median(fares), 2), "observations": len(rows),
            "airlines_available": len({r.airline for r in rows}), "sources_available": len({r.source_portal for r in rows}), "weekly_change": route_change,
            "trend": [{"date": key, "average_fare": round(sum(vals) / len(vals), 2)} for key, vals in trend_groups.items()],
            "lead_time": lead_time_rows(db, origin, destination), "airlines": _group_average(rows, "airline"), "sources": _group_average(rows, "source_portal")}


@router.get("/lead-time", summary="Advance-purchase fare curve")
def lead_time(origin: str | None = None, destination: str | None = None, airline: str | None = None, source: str | None = None, db: Session = Depends(get_db_session)):
    items = lead_time_rows(db, origin, destination, airline, source)
    first = next((i["average_fare"] for i in items if i["advance_days"] == 1), None)
    thirty = next((i["average_fare"] for i in items if i["advance_days"] == 30), None)
    saving = round((first - thirty) / first * 100, 1) if first and thirty else None
    return {"items": items, "t30_saving_vs_t1_percent": saving,
            "insight": f"Booking 30 days in advance was {saving}% cheaper than booking one day in advance for the selected data." if saving is not None else None}


@router.get("/sources/status", summary="Airline and collection-source health")
def sources_status(db: Session = Depends(get_db_session)):
    airlines = db.query(FlightPrice.airline, func.count(FlightPrice.id), func.count(func.distinct(FlightPrice.origin + FlightPrice.destination)), func.avg(FlightPrice.total_fare), func.min(FlightPrice.total_fare), func.max(FlightPrice.scraped_at)).group_by(FlightPrice.airline).all()
    return {"sources": source_statuses(db), "airlines": [{"airline": r[0], "records": r[1], "routes_covered": r[2], "average_fare": round(r[3], 2), "lowest_fare": r[4], "latest_observation": r[5].isoformat()} for r in airlines]}


@router.get("/coverage", summary="Route/source and advance-window coverage")
def coverage(db: Session = Depends(get_db_session)):
    available = {(r.origin, r.destination, r.source_portal) for r in db.query(FlightPrice.origin, FlightPrice.destination, FlightPrice.source_portal).distinct().all()}
    matrix = [{"route": route.code, "sources": {source: (route.origin, route.destination, source) in available for source in CONFIGURED_SOURCES}} for route in ROUTE_BASKET]
    return {"matrix": matrix, "advance_windows": lead_time_rows(db)}


@router.get("/data-quality", summary="Cleaning and validation quality metrics")
def data_quality(db: Session = Depends(get_db_session)):
    raw = db.query(func.count(FlightPrice.id)).scalar() or 0
    outliers = db.query(func.count(FlightPrice.id)).filter(FlightPrice.is_outlier.is_(True)).scalar() or 0
    missing = db.query(func.count(FlightPrice.id)).filter((FlightPrice.base_fare.is_(None)) | (FlightPrice.taxes_fees.is_(None))).scalar() or 0
    by_source = db.query(FlightPrice.source_portal, func.count(FlightPrice.id), func.sum(func.cast(FlightPrice.base_fare.is_(None), Integer))).group_by(FlightPrice.source_portal).all()
    outlier_routes = db.query(FlightPrice.origin, FlightPrice.destination, func.count(FlightPrice.id)).filter(FlightPrice.is_outlier.is_(True)).group_by(FlightPrice.origin, FlightPrice.destination).all()
    return {"raw_records": raw, "valid_records": raw - outliers, "duplicates_removed": None, "duplicates_note": "Not persisted by the current normalization audit log.",
            "outliers_detected": outliers, "missing_fare_breakdowns": missing, "usable_index_observations": raw - outliers,
            "missing_by_source": [{"source": r[0], "records": r[1], "missing": int(r[2] or 0)} for r in by_source],
            "outliers_by_route": [{"route": f"{r[0]}-{r[1]}", "outliers": r[2]} for r in outlier_routes], "advance_window_coverage": lead_time_rows(db)}


@router.get("/fares", summary="Paginated fare observations")
def fares(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), origin: str | None = None, destination: str | None = None,
          airline: str | None = None, source: str | None = None, travel_date: date | None = None, scraped_date: date | None = None,
          advance_window: int | None = None, outlier: bool | None = None, db: Session = Depends(get_db_session)):
    query = _apply_filters(db.query(FlightPrice), origin, destination, airline, source, travel_date, scraped_date, advance_window, outlier)
    total = query.count()
    rows = query.order_by(FlightPrice.scraped_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_fare_dict(row) for row in rows], "page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size}


@router.get("/fares/export", summary="Export filtered fares")
def export_fares(format: Literal["csv", "json"] = "csv", origin: str | None = None, destination: str | None = None, airline: str | None = None, source: str | None = None, db: Session = Depends(get_db_session)):
    data = [_fare_dict(row) for row in _apply_filters(db.query(FlightPrice), origin, destination, airline, source).order_by(FlightPrice.scraped_at.desc()).all()]
    if format == "json":
        return StreamingResponse(io.BytesIO(json.dumps(data, indent=2).encode()), media_type="application/json", headers={"Content-Disposition": "attachment; filename=airfares.json"})
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys()); writer.writeheader(); writer.writerows(data)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=airfares.csv"})


@router.get("/runs/recent", summary="Recent collection audit runs")
def recent_runs(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db_session)):
    runs = db.query(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(limit).all()
    return [{"id": r.id, "portal": r.source_portal, "route": f"{r.origin}-{r.destination}", "travel_date": r.travel_date.isoformat(),
             "status": r.status, "records": r.records_inserted, "started_at": r.started_at.isoformat(),
             "duration_s": round(r.duration_seconds(), 1) if r.duration_seconds() is not None else None, "error": r.error_message} for r in runs]


@router.get("/runs/summary", summary="Collection engine daily summary")
def runs_summary(db: Session = Depends(get_db_session)):
    rows = db.query(ScrapeRun).filter(func.date(ScrapeRun.started_at) == datetime.utcnow().date()).all()
    durations = [r.duration_seconds() for r in rows if r.duration_seconds() is not None]
    return {"jobs_today": len(rows), "successful": sum(r.status == "SUCCESS" for r in rows), "failed": sum(r.status in {"FAILED", "BLOCKED", "OFFLINE", "INTERRUPTED"} for r in rows),
            "partial": sum(r.status == "PARTIAL" for r in rows), "running": sum(r.status == "RUNNING" for r in rows),
            "records_collected": sum(r.records_inserted for r in rows), "average_run_duration": round(sum(durations) / len(durations), 1) if durations else None}


@router.get("/methodology", summary="Index methodology disclosure")
def methodology():
    return {**METHODOLOGY, "base_period": settings.index_base_period, "route_count": len(ROUTE_BASKET), "advance_windows": LEAD_WINDOWS,
            "freshness_thresholds_hours": {"fresh": settings.freshness_fresh_hours, "delayed": settings.freshness_delayed_hours}}


def _backtesting_result(db: Session):
    reference_path = settings.data_dir / "reference_fares.csv"
    required = ["date", "route", "reference_fare"]
    if not reference_path.exists():
        return {"status": "NO_REFERENCE_DATASET", "message": "No reference dataset imported.", "required_columns": required, "items": [], "mae": None, "mape": None, "coverage": None}
    with reference_path.open(newline="", encoding="utf-8") as handle:
        references = list(csv.DictReader(handle))
    collected = {(str(r.travel_date), f"{r.origin}-{r.destination}"): float(r.average) for r in db.query(
        FlightPrice.travel_date, FlightPrice.origin, FlightPrice.destination, func.avg(FlightPrice.total_fare).label("average")
    ).filter(FlightPrice.is_outlier.is_(False)).group_by(FlightPrice.travel_date, FlightPrice.origin, FlightPrice.destination).all()}
    items = []
    for row in references:
        reference = float(row["reference_fare"])
        average = collected.get((row["date"], row["route"]))
        difference = average - reference if average is not None else None
        items.append({**row, "reference_fare": reference, "collected_average": round(average, 2) if average is not None else None,
                      "difference": round(difference, 2) if difference is not None else None,
                      "percentage_error": round(abs(difference) / reference * 100, 2) if difference is not None and reference else None})
    matched = [item for item in items if item["difference"] is not None]
    return {"status": "READY", "message": f"{len(matched)} of {len(items)} reference rows matched.", "required_columns": required, "items": items,
            "mae": round(sum(abs(item["difference"]) for item in matched) / len(matched), 2) if matched else None,
            "mape": round(sum(item["percentage_error"] for item in matched) / len(matched), 2) if matched else None,
            "coverage": round(len(matched) / len(items) * 100, 2) if items else 0}


@router.get("/backtesting", summary="Backtesting results")
def backtesting_status(db: Session = Depends(get_db_session)):
    return _backtesting_result(db)


@router.post("/backtesting/import", summary="Import a reference CSV")
async def import_backtesting(file: UploadFile = File(...), db: Session = Depends(get_db_session)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "A CSV file is required.")
    content = await file.read()
    if len(content) > 5_000_000:
        raise HTTPException(413, "Reference CSV must be smaller than 5 MB.")
    try:
        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "CSV must be UTF-8 encoded.") from exc
    required = {"date", "route", "reference_fare"}
    if not rows or not required.issubset(rows[0]):
        raise HTTPException(400, "CSV columns must be date, route, reference_fare.")
    normalized = []
    try:
        for row in rows:
            observed_date = date.fromisoformat(row["date"].strip()).isoformat()
            route = row["route"].strip().upper()
            if len(route) != 7 or route[3] != "-":
                raise ValueError("invalid route")
            fare = float(row["reference_fare"])
            if fare <= 0:
                raise ValueError("invalid fare")
            normalized.append({"date": observed_date, "route": route, "reference_fare": fare})
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "Rows require ISO date, ORG-DST route and positive reference_fare.") from exc
    reference_path = settings.data_dir / "reference_fares.csv"
    with reference_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "route", "reference_fare"]); writer.writeheader(); writer.writerows(normalized)
    return _backtesting_result(db)


@router.get("/stats", include_in_schema=False)
def legacy_stats(db: Session = Depends(get_db_session)):
    data = overview(db)
    return {"totalFares": data["data_points"], "totalRuns": db.query(ScrapeRun).count(), "successRate": 0, "faresToday": 0}
