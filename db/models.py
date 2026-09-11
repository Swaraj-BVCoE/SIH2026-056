"""
db/models.py
─────────────
SQLAlchemy ORM models for the AirFare scraper.

FlightPrice  — one row per scraped fare observation
ScrapeRun    — audit log for each scheduled/manual scrape job
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# FlightPrice — core fact table
# ─────────────────────────────────────────────────────────────────────────────
class FlightPrice(Base):
    """
    One row = one fare observation for a specific flight on a specific
    search date.  Multiple rows can exist for the same flight/date if
    scraped at different times (tracking price changes).
    """

    __tablename__ = "flight_prices"

    # ── Primary key ──────────────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── When was this collected? ──────────────────────────────────────────────
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="UTC timestamp when this record was collected",
    )

    # ── Route ─────────────────────────────────────────────────────────────────
    origin: Mapped[str] = mapped_column(String(3), nullable=False, comment="IATA origin code")
    destination: Mapped[str] = mapped_column(String(3), nullable=False, comment="IATA destination code")
    travel_date: Mapped[date] = mapped_column(Date, nullable=False, comment="Date of the flight")

    # ── Flight details ────────────────────────────────────────────────────────
    airline: Mapped[str] = mapped_column(String(64), nullable=False, comment="Airline name (normalized)")
    airline_code: Mapped[Optional[str]] = mapped_column(String(4), nullable=True, comment="IATA airline code e.g. 6E")
    flight_number: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment="e.g. 6E-123")
    departure_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    arrival_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stops: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, comment="0=nonstop, 1=1-stop, etc.")

    # ── Fare ─────────────────────────────────────────────────────────────────
    fare_class: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Economy",
        comment="Economy / Business / Premium Economy"
    )
    base_fare: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Base fare before taxes (INR)")
    taxes_fees: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Taxes and surcharges (INR)")
    total_fare: Mapped[float] = mapped_column(Float, nullable=False, comment="All-inclusive total fare (INR)")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    seats_left: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True, comment="Seats available at this price")

    # ── Source ────────────────────────────────────────────────────────────────
    source_portal: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="e.g. indigo_direct / air_india_direct / makemytrip / cleartrip"
    )
    advance_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False,
        comment="Number of days between scrape date and travel date"
    )

    # ── Quality flags ────────────────────────────────────────────────────────
    is_outlier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_refundable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # ── Raw payload (for reprocessing) ───────────────────────────────────────
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="JSON string of raw scraped payload")

    # ── Scrape run FK ─────────────────────────────────────────────────────────
    scrape_run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("scrape_runs.id"), nullable=True, comment="FK to scrape_runs.id"
    )

    # ── Indexes ──────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_fp_route_date", "origin", "destination", "travel_date"),
        Index("ix_fp_scraped_at", "scraped_at"),
        Index("ix_fp_airline", "airline"),
        Index("ix_fp_source", "source_portal"),
        Index("ix_fp_advance", "advance_days"),
    )

    def raw_payload(self) -> dict:
        """Deserialize raw_json back to a dict."""
        return json.loads(self.raw_json) if self.raw_json else {}

    def __repr__(self) -> str:
        return (
            f"<FlightPrice {self.origin}→{self.destination} "
            f"{self.travel_date} {self.airline} ₹{self.total_fare:.0f}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ScrapeRun — audit log
# ─────────────────────────────────────────────────────────────────────────────
class ScrapeRun(Base):
    """
    Records metadata for each scraping job — useful for monitoring,
    debugging, and computing coverage statistics.
    """

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Job params ────────────────────────────────────────────────────────────
    source_portal: Mapped[str] = mapped_column(String(32), nullable=False)
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    travel_date: Mapped[date] = mapped_column(Date, nullable=False)

    # ── Result ────────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="RUNNING",
        comment="RUNNING / SUCCESS / FAILED / BLOCKED"
    )
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    proxy_used: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_sr_portal_status", "source_portal", "status"),
        Index("ix_sr_started", "started_at"),
    )

    def duration_seconds(self) -> Optional[float]:
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def __repr__(self) -> str:
        return (
            f"<ScrapeRun [{self.status}] {self.source_portal} "
            f"{self.origin}-{self.destination} {self.travel_date}>"
        )


class IndexObservation(Base):
    """Optional materialized national index observation for scheduled jobs."""

    __tablename__ = "index_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    index_value: Mapped[float] = mapped_column(Float, nullable=False)
    base_period: Mapped[str] = mapped_column(String(64), nullable=False)
    routes_included: Mapped[int] = mapped_column(Integer, nullable=False)
    records_used: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("date", "frequency", "base_period", name="uq_index_observation_period"),
        Index("ix_index_date_frequency", "date", "frequency"),
    )


class RouteIndexObservation(Base):
    """Optional materialized route-level price relative and contribution."""

    __tablename__ = "route_index_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    avg_fare: Mapped[float] = mapped_column(Float, nullable=False)
    base_fare: Mapped[float] = mapped_column(Float, nullable=False)
    price_relative: Mapped[float] = mapped_column(Float, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    weighted_contribution: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (
        UniqueConstraint("date", "origin", "destination", name="uq_route_index_observation"),
        Index("ix_route_index_date_route", "date", "origin", "destination"),
    )
