"""
pipeline/storage.py
────────────────────
Handles batch upsert of validated FlightPrice records into the database.

Features:
  - Batch insert with duplicate detection
  - Upsert logic (skip if exact duplicate exists)
  - Returns count of new records inserted
"""

from __future__ import annotations

import json
from datetime import date
from typing import Optional

from loguru import logger
from sqlalchemy import select, and_

from db.database import get_db
from db.models import FlightPrice, ScrapeRun
from pipeline.validator import FlightPriceSchema


def save_records(
    validated: list[FlightPriceSchema],
    scrape_run_id: Optional[int] = None,
) -> int:
    """
    Insert validated flight price records into the database.

    Deduplication: A record is considered a duplicate if the same
    (origin, destination, travel_date, flight_number, source_portal, scraped_at_day)
    already exists. Duplicates are skipped.

    Returns:
        Number of new records inserted.
    """
    if not validated:
        return 0

    inserted = 0

    with get_db() as db:
        for schema in validated:
            try:
                # Check for duplicate (same flight on same scrape day)
                stmt = select(FlightPrice).where(
                    and_(
                        FlightPrice.origin == schema.origin,
                        FlightPrice.destination == schema.destination,
                        FlightPrice.travel_date == schema.travel_date,
                        FlightPrice.source_portal == schema.source_portal,
                        FlightPrice.flight_number == schema.flight_number,
                        # Same calendar day
                        FlightPrice.scraped_at >= schema.scraped_at.replace(
                            hour=0, minute=0, second=0, microsecond=0
                        ),
                    )
                )
                existing = db.execute(stmt).scalars().first()

                if existing:
                    # Update fare if the new price is different (price changed)
                    if abs(existing.total_fare - schema.total_fare) > 0.01:
                        existing.total_fare = schema.total_fare
                        existing.base_fare = schema.base_fare
                        existing.taxes_fees = schema.taxes_fees
                        existing.scraped_at = schema.scraped_at
                        existing.seats_left = schema.seats_left
                        inserted += 1  # Count as update = meaningful change
                    # else: exact same price — skip
                    continue

                # New record
                record = FlightPrice(
                    scraped_at=schema.scraped_at,
                    travel_date=schema.travel_date,
                    origin=schema.origin,
                    destination=schema.destination,
                    airline=schema.airline,
                    airline_code=schema.airline_code,
                    flight_number=schema.flight_number,
                    departure_time=schema.departure_time,
                    arrival_time=schema.arrival_time,
                    duration_minutes=schema.duration_minutes,
                    stops=schema.stops,
                    fare_class=schema.fare_class,
                    base_fare=schema.base_fare,
                    taxes_fees=schema.taxes_fees,
                    total_fare=schema.total_fare,
                    currency=schema.currency,
                    seats_left=schema.seats_left,
                    source_portal=schema.source_portal,
                    advance_days=schema.advance_days,
                    is_outlier=schema.is_outlier,
                    is_refundable=schema.is_refundable,
                    raw_json=schema.raw_json,
                    scrape_run_id=scrape_run_id,
                )
                db.add(record)
                inserted += 1

            except Exception as exc:
                logger.error("[storage] Error saving record: {}", exc)
                continue

    logger.info("[storage] Inserted/updated {} records.", inserted)
    return inserted


def get_daily_summary(query_date: Optional[date] = None) -> list[dict]:
    """
    Return a summary of collected fares for a given date.
    Groups by route + airline and returns min/avg/max fare.
    """
    from datetime import datetime, timezone
    from sqlalchemy import func

    query_date = query_date or datetime.now(tz=timezone.utc).date()

    with get_db() as db:
        results = (
            db.query(
                FlightPrice.origin,
                FlightPrice.destination,
                FlightPrice.airline,
                func.count(FlightPrice.id).label("count"),
                func.min(FlightPrice.total_fare).label("min_fare"),
                func.avg(FlightPrice.total_fare).label("avg_fare"),
                func.max(FlightPrice.total_fare).label("max_fare"),
            )
            .filter(FlightPrice.travel_date == query_date)
            .filter(FlightPrice.is_outlier == False)
            .group_by(
                FlightPrice.origin,
                FlightPrice.destination,
                FlightPrice.airline,
            )
            .order_by(FlightPrice.origin, FlightPrice.destination, FlightPrice.airline)
            .all()
        )

    return [
        {
            "route": f"{r.origin}-{r.destination}",
            "airline": r.airline,
            "count": r.count,
            "min_fare": round(r.min_fare, 2),
            "avg_fare": round(r.avg_fare, 2),
            "max_fare": round(r.max_fare, 2),
        }
        for r in results
    ]
