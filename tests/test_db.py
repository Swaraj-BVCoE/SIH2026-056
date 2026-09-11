"""
tests/test_db.py
─────────────────
Integration tests for DB write/read round-trips.
Uses an in-memory SQLite database to avoid touching the real DB.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, FlightPrice, ScrapeRun


# ── Test fixtures ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="function")
def test_engine():
    """Create a fresh in-memory SQLite DB for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(test_engine):
    """Provide a test session that rolls back after each test."""
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


# ── FlightPrice model tests ───────────────────────────────────────────────────
class TestFlightPriceModel:
    def test_create_and_read(self, db_session):
        """Insert a FlightPrice and read it back."""
        record = FlightPrice(
            scraped_at=datetime.now(tz=timezone.utc),
            travel_date=date(2026, 10, 15),
            origin="DEL",
            destination="BOM",
            airline="IndiGo",
            airline_code="6E",
            flight_number="6E-234",
            total_fare=4500.0,
            source_portal="indigo_direct",
            advance_days=30,
        )
        db_session.add(record)
        db_session.commit()

        fetched = db_session.get(FlightPrice, record.id)
        assert fetched is not None
        assert fetched.origin == "DEL"
        assert fetched.destination == "BOM"
        assert fetched.total_fare == 4500.0
        assert fetched.airline == "IndiGo"

    def test_repr(self, db_session):
        record = FlightPrice(
            scraped_at=datetime.now(tz=timezone.utc),
            travel_date=date(2026, 10, 15),
            origin="DEL",
            destination="BOM",
            airline="IndiGo",
            total_fare=4500.0,
            source_portal="indigo_direct",
            advance_days=30,
        )
        db_session.add(record)
        db_session.commit()
        assert "DEL→BOM" in repr(record)
        assert "IndiGo" in repr(record)

    def test_multiple_prices_same_route(self, db_session):
        """Multiple fares for the same route should coexist."""
        records = [
            FlightPrice(
                scraped_at=datetime.now(tz=timezone.utc),
                travel_date=date(2026, 10, 15),
                origin="DEL",
                destination="BOM",
                airline="IndiGo",
                total_fare=4500.0,
                source_portal="indigo_direct",
                advance_days=30,
            ),
            FlightPrice(
                scraped_at=datetime.now(tz=timezone.utc),
                travel_date=date(2026, 10, 15),
                origin="DEL",
                destination="BOM",
                airline="Air India",
                total_fare=6800.0,
                source_portal="air_india_direct",
                advance_days=30,
            ),
        ]
        db_session.add_all(records)
        db_session.commit()

        count = db_session.query(FlightPrice).filter(
            FlightPrice.origin == "DEL",
            FlightPrice.destination == "BOM",
        ).count()
        assert count == 2


# ── ScrapeRun model tests ─────────────────────────────────────────────────────
class TestScrapeRunModel:
    def test_create_run(self, db_session):
        run = ScrapeRun(
            started_at=datetime.now(tz=timezone.utc),
            source_portal="indigo_direct",
            origin="DEL",
            destination="BOM",
            travel_date=date(2026, 10, 15),
            status="SUCCESS",
            records_inserted=42,
        )
        db_session.add(run)
        db_session.commit()

        fetched = db_session.get(ScrapeRun, run.id)
        assert fetched is not None
        assert fetched.status == "SUCCESS"
        assert fetched.records_inserted == 42

    def test_duration_seconds(self, db_session):
        from datetime import timedelta
        start = datetime.now(tz=timezone.utc)
        run = ScrapeRun(
            started_at=start,
            finished_at=start + timedelta(seconds=45),
            source_portal="makemytrip",
            origin="BOM",
            destination="BLR",
            travel_date=date(2026, 10, 15),
            status="SUCCESS",
        )
        db_session.add(run)
        db_session.commit()

        assert run.duration_seconds() == pytest.approx(45.0, abs=1.0)

    def test_repr(self, db_session):
        run = ScrapeRun(
            started_at=datetime.now(tz=timezone.utc),
            source_portal="cleartrip",
            origin="DEL",
            destination="BLR",
            travel_date=date(2026, 10, 15),
            status="FAILED",
        )
        db_session.add(run)
        db_session.commit()
        assert "FAILED" in repr(run)
        assert "cleartrip" in repr(run)
