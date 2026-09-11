"""
tests/test_normalizer.py
─────────────────────────
Unit tests for the data normalization pipeline.
"""

from __future__ import annotations

from datetime import date

import pytest

from pipeline.normalizer import (
    normalize_airline_name,
    normalize_iata,
    parse_time_str,
    parse_duration,
    compute_advance_days,
    normalize_fare_record,
    normalize_batch,
)
from scraper.base_scraper import FareRecord

ROUTE_ORIGIN = "DEL"
ROUTE_DEST = "BOM"
TRAVEL_DATE = date(2026, 10, 15)
SCRAPE_DATE = date(2026, 9, 15)


# ── Airline name normalization ────────────────────────────────────────────────
class TestAirlineNormalization:
    def test_by_iata_code(self):
        assert normalize_airline_name("IndiGo", "6E") == "IndiGo"
        assert normalize_airline_name("Express", "IX") == "Air India Express"

    def test_by_name_alias(self):
        assert normalize_airline_name("spicejet", "") == "SpiceJet"
        assert normalize_airline_name("GoIndigo", "") == "IndiGo"

    def test_unknown_returns_raw(self):
        assert normalize_airline_name("SomeNewAirline", "") == "SomeNewAirline"

    def test_code_takes_priority(self):
        assert normalize_airline_name("anything", "AI") == "Air India"


# ── IATA validation ───────────────────────────────────────────────────────────
class TestIATAValidation:
    def test_valid_codes(self):
        assert normalize_iata("DEL") == "DEL"
        assert normalize_iata("bom") == "BOM"  # Case insensitive

    def test_invalid_code(self):
        assert normalize_iata("XYZ") is None
        assert normalize_iata("") is None
        assert normalize_iata("DELHI") is None


# ── Time parsing ──────────────────────────────────────────────────────────────
class TestTimeParsing:
    def test_hhmm(self):
        t = parse_time_str("06:45")
        assert t is not None
        assert t.hour == 6
        assert t.minute == 45

    def test_hhmmss(self):
        t = parse_time_str("14:30:00")
        assert t is not None
        assert t.hour == 14

    def test_empty(self):
        assert parse_time_str("") is None
        assert parse_time_str(None) is None

    def test_invalid(self):
        assert parse_time_str("25:99") is None or parse_time_str("25:99") is not None
        # Should not raise


# ── Duration parsing ──────────────────────────────────────────────────────────
class TestDurationParsing:
    def test_integer(self):
        assert parse_duration(90) == 90

    def test_hours_minutes_string(self):
        assert parse_duration("2h 30m") == 150
        assert parse_duration("2h30m") == 150

    def test_hours_only(self):
        assert parse_duration("3h") == 180

    def test_minutes_only(self):
        assert parse_duration("120m") == 120
        assert parse_duration("120") == 120

    def test_empty(self):
        assert parse_duration("") == 0
        assert parse_duration(0) == 0


# ── Advance days ──────────────────────────────────────────────────────────────
class TestAdvanceDays:
    def test_30_days_ahead(self):
        assert compute_advance_days(SCRAPE_DATE, TRAVEL_DATE) == 30

    def test_same_day(self):
        assert compute_advance_days(TRAVEL_DATE, TRAVEL_DATE) == 0

    def test_past_date(self):
        # Past travel date should return 0 (not negative)
        past = date(2026, 8, 1)
        assert compute_advance_days(SCRAPE_DATE, past) == 0


# ── Full record normalization ─────────────────────────────────────────────────
class TestNormalizeFareRecord:
    def _make_record(self, **kwargs):
        defaults = dict(
            origin="DEL",
            destination="BOM",
            travel_date=TRAVEL_DATE,
            airline="IndiGo",
            airline_code="6E",
            flight_number="6E-234",
            departure_time="06:00",
            arrival_time="08:10",
            duration_minutes=130,
            stops=0,
            fare_class="Economy",
            base_fare=3800.0,
            taxes_fees=700.0,
            total_fare=4500.0,
            currency="INR",
        )
        defaults.update(kwargs)
        return FareRecord(**defaults)

    def test_valid_record(self):
        record = self._make_record()
        result = normalize_fare_record(record, "indigo_direct", SCRAPE_DATE)
        assert result is not None
        assert result["airline"] == "IndiGo"
        assert result["total_fare"] == 4500.0
        assert result["advance_days"] == 30

    def test_zero_fare_rejected(self):
        record = self._make_record(total_fare=0)
        result = normalize_fare_record(record, "indigo_direct", SCRAPE_DATE)
        assert result is None

    def test_invalid_iata_rejected(self):
        record = self._make_record(origin="DELHI")
        result = normalize_fare_record(record, "indigo_direct", SCRAPE_DATE)
        assert result is None

    def test_airline_name_normalized(self):
        record = self._make_record(airline="6E", airline_code="6E")
        result = normalize_fare_record(record, "indigo_direct", SCRAPE_DATE)
        assert result is not None
        assert result["airline"] == "IndiGo"


# ── Batch normalization ───────────────────────────────────────────────────────
class TestNormalizeBatch:
    def test_deduplication(self):
        """Same flight with two prices → keep cheapest."""
        records = [
            FareRecord(
                origin="DEL", destination="BOM", travel_date=TRAVEL_DATE,
                airline="IndiGo", airline_code="6E", flight_number="6E-234",
                departure_time="06:00", arrival_time="08:10",
                total_fare=4500.0, fare_class="Economy",
            ),
            FareRecord(
                origin="DEL", destination="BOM", travel_date=TRAVEL_DATE,
                airline="IndiGo", airline_code="6E", flight_number="6E-234",
                departure_time="06:00", arrival_time="08:10",
                total_fare=4200.0, fare_class="Economy",
            ),
        ]
        result = normalize_batch(records, "indigo_direct", SCRAPE_DATE)
        # Should keep only the cheaper one
        assert len(result) == 1
        assert result[0]["total_fare"] == 4200.0

    def test_batch_with_invalid_records(self):
        """Invalid records should be filtered out."""
        records = [
            FareRecord(
                origin="DEL", destination="BOM", travel_date=TRAVEL_DATE,
                airline="IndiGo", total_fare=4500.0,
            ),
            FareRecord(
                origin="DEL", destination="BOM", travel_date=TRAVEL_DATE,
                airline="IndiGo", total_fare=0.0,  # Invalid
            ),
        ]
        result = normalize_batch(records, "indigo_direct", SCRAPE_DATE)
        assert len(result) == 1
