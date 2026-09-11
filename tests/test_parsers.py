"""
tests/test_parsers.py
──────────────────────
Unit tests for scraper parsers using saved fixture data.
Tests the XHR parsing logic WITHOUT launching a real browser.
"""

from __future__ import annotations

from datetime import date

import pytest

from config.routes import Route
from scraper.airlines.indigo import IndigoScraper
from scraper.airlines.air_india import AirIndiaScraper
from scraper.airlines.akasa import AkasaScraper
from scraper.airlines.spicejet import SpiceJetScraper
from scraper.otas.makemytrip import MakeMyTripScraper
from scraper.otas.cleartrip import CleartripScraper
from scraper.airlines.air_india import SEARCH_URLS as AIR_INDIA_URLS
from scraper.airlines.akasa import SEARCH_URLS as AKASA_URLS
from scraper.airlines.spicejet import SEARCH_URLS as SPICEJET_URLS
from scraper.otas.easemytrip import SEARCH_DATE_FORMAT as EASEMYTRIP_DATE_FORMAT


ROUTE = Route("DEL", "BOM")
TRAVEL_DATE = date(2026, 10, 15)


# ── IndiGo Parser Tests ───────────────────────────────────────────────────────
class TestIndigoParser:
    def setup_method(self):
        self.scraper = IndigoScraper()

    def test_parse_itinerary_basic(self):
        """Test standard IndiGo itinerary XHR response."""
        fixture = {
            "itineraries": [
                {
                    "totalFare": 4500.0,
                    "baseFare": 3800.0,
                    "segments": [
                        {
                            "flightNumber": "234",
                            "departureTime": "06:00",
                            "arrivalTime": "08:10",
                        }
                    ],
                    "durationInMinutes": 130,
                    "stops": 0,
                    "fareClass": "Economy",
                    "seatsAvailable": 3,
                }
            ]
        }
        records = self.scraper._extract_from_xhr(fixture, ROUTE, TRAVEL_DATE)
        assert len(records) == 1
        r = records[0]
        assert r.airline == "IndiGo"
        assert r.airline_code == "6E"
        assert r.total_fare == 4500.0
        assert r.base_fare == 3800.0
        assert r.flight_number == "6E-234"
        assert r.departure_time == "06:00"
        assert r.stops == 0

    def test_parse_empty_response(self):
        """Empty response should yield no records."""
        records = self.scraper._extract_from_xhr({}, ROUTE, TRAVEL_DATE)
        assert records == []

    def test_parse_missing_fare(self):
        """Record with no fare should be skipped."""
        fixture = {"itineraries": [{"segments": [{"flightNumber": "100"}]}]}
        records = self.scraper._extract_from_xhr(fixture, ROUTE, TRAVEL_DATE)
        assert records == []

    def test_parse_card_text(self):
        """Test HTML card text parsing."""
        text = "6E-345  06:00  →  08:10  ₹4,299  Economy  Non-stop"
        record = self.scraper._parse_card_text(text, ROUTE, TRAVEL_DATE)
        assert record is not None
        assert record.total_fare == 4299.0
        assert record.flight_number == "6E-345"


# ── Air India Parser Tests ────────────────────────────────────────────────────
class TestAirIndiaParser:
    def setup_method(self):
        self.scraper = AirIndiaScraper()

    def test_parse_flight_basic(self):
        fixture_flight = {
            "totalFare": 6800.0,
            "baseFare": 5500.0,
            "flightNumber": "AI-456",
            "segments": [
                {
                    "flightNumber": "456",
                    "departureTime": "09:30",
                    "arrivalTime": "11:45",
                }
            ],
            "durationInMinutes": 135,
        }
        record = self.scraper._parse_flight(fixture_flight, ROUTE, TRAVEL_DATE)
        assert record is not None
        assert record.airline == "Air India"
        assert record.total_fare == 6800.0

    def test_detect_air_india_express(self):
        """IX flights should be tagged as Air India Express."""
        fixture_flight = {
            "totalFare": 3500.0,
            "flightNumber": "IX-234",
            "operatingCarrier": "Air India Express",
            "segments": [],
        }
        record = self.scraper._parse_flight(fixture_flight, ROUTE, TRAVEL_DATE)
        assert record is not None
        assert record.airline == "Air India Express"
        assert record.airline_code == "IX"

    def test_uses_current_booking_entry_point(self):
        assert AIR_INDIA_URLS[0].endswith("/in/en/book/search-flights.html")


class TestSourceEntryPoints:
    def test_akasa_uses_current_booking_page(self):
        assert AKASA_URLS[0].endswith("/flight-booking")

    def test_spicejet_prefers_booking_host(self):
        assert SPICEJET_URLS[0] == "https://book.spicejet.com/"

    def test_easemytrip_uses_day_first_search_date(self):
        assert TRAVEL_DATE.strftime(EASEMYTRIP_DATE_FORMAT) == "15/10/2026"

    def test_reference_api_lists_are_ignored(self):
        assert AkasaScraper()._extract_from_xhr([], ROUTE, TRAVEL_DATE) == []

    def test_akasa_navitaire_availability_response(self):
        fixture = {
            "data": {
                "results": [{
                    "trips": [{
                        "journeysAvailableByMarket": {
                            "DEL|BOM": [{
                                "segments": [{
                                    "identifier": {"carrierCode": "QP", "identifier": "1123"},
                                    "designator": {
                                        "departure": "2026-10-15T06:05:00",
                                        "arrival": "2026-10-15T08:15:00",
                                    },
                                    "fares": [{
                                        "productClass": "EC",
                                        "passengerFares": [{
                                            "fareAmount": 4000,
                                            "serviceCharges": [
                                                {"amount": 4000},
                                                {"amount": 750},
                                            ],
                                        }],
                                    }],
                                }],
                            }],
                        },
                    }],
                }],
            },
        }
        records = AkasaScraper()._extract_from_xhr(fixture, ROUTE, TRAVEL_DATE)
        assert len(records) == 1
        assert records[0].flight_number == "QP-1123"
        assert records[0].total_fare == 4750
        assert records[0].departure_time == "06:05"


# ── MakeMyTrip Parser Tests ───────────────────────────────────────────────────
class TestMakeMyTripParser:
    def setup_method(self):
        self.scraper = MakeMyTripScraper()

    def test_parse_trip_infos(self):
        """Test MMT's tripInfos[] XHR structure."""
        fixture = {
            "data": {
                "tripInfos": [
                    {
                        "sI": [
                            {
                                "fD": {"aI": {"code": "6E"}, "fN": "234"},
                                "dt": "06:00",
                                "at": "08:10",
                            }
                        ],
                        "tt": 130,
                        "totalPriceList": [
                            {
                                "fd": {
                                    "ADULT": {
                                        "fC": {"TF": 4500, "BF": 3800},
                                        "cc": "ECONOMY",
                                    }
                                }
                            }
                        ],
                    }
                ]
            }
        }
        records = self.scraper._extract_from_xhr(fixture, ROUTE, TRAVEL_DATE)
        assert len(records) == 1
        r = records[0]
        assert r.airline == "IndiGo"
        assert r.total_fare == 4500
        assert r.base_fare == 3800

    def test_parse_empty(self):
        records = self.scraper._extract_from_xhr({}, ROUTE, TRAVEL_DATE)
        assert records == []


# ── Cleartrip Parser Tests ────────────────────────────────────────────────────
class TestCleartripParser:
    def setup_method(self):
        self.scraper = CleartripScraper()

    def test_parse_results_outbound(self):
        fixture = {
            "results": {
                "outbound": [
                    {
                        "fare": {"totalFare": 5200.0, "baseFare": 4100.0},
                        "segments": [
                            {
                                "carrier": "6E",
                                "flightNumber": "789",
                                "departureTime": "14:00",
                                "arrivalTime": "16:15",
                            }
                        ],
                        "duration": 135,
                    }
                ]
            }
        }
        records = self.scraper._extract_from_xhr(fixture, ROUTE, TRAVEL_DATE)
        assert len(records) == 1
        r = records[0]
        assert r.airline == "IndiGo"
        assert r.total_fare == 5200.0
