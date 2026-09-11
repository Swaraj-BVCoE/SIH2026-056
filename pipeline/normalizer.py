"""
pipeline/normalizer.py
───────────────────────
Normalizes raw FareRecord objects before DB insertion.

Responsibilities:
  - Standardize airline names (code aliases → canonical name)
  - Validate + normalize IATA codes
  - Convert duration strings to minutes
  - Parse HH:MM time strings to time objects
  - Compute advance_days
  - Deduplicate within a batch (keep cheapest per flight+time)
  - Flag statistical outliers (±3σ from rolling mean)
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, time, timezone
from typing import Optional

from loguru import logger

from config.routes import AIRPORTS
from scraper.base_scraper import FareRecord

# ── Airline name normalization ────────────────────────────────────────────────
AIRLINE_CANONICAL: dict[str, str] = {
    # By IATA code
    "6E": "IndiGo",
    "AI": "Air India",
    "IX": "Air India Express",
    "QP": "Akasa Air",
    "SG": "SpiceJet",
    "UK": "Vistara",
    "I5": "AirAsia India",
    "G8": "Go First",
    # By alias strings (lowercase)
    "indigo": "IndiGo",
    "go indigo": "IndiGo",
    "air india": "Air India",
    "air india express": "Air India Express",
    "akasa": "Akasa Air",
    "akasa air": "Akasa Air",
    "spicejet": "SpiceJet",
    "spice jet": "SpiceJet",
    "vistara": "Vistara",
    "go first": "Go First",
    "gofirst": "Go First",
    "airasia": "AirAsia India",
    "air asia": "AirAsia India",
}


def normalize_airline_name(raw_name: str, airline_code: str = "") -> str:
    """Return canonical airline name."""
    # Try by code first
    if airline_code and airline_code.upper() in AIRLINE_CANONICAL:
        return AIRLINE_CANONICAL[airline_code.upper()]
    # Try by name
    lower = raw_name.strip().lower()
    for alias, canonical in AIRLINE_CANONICAL.items():
        if alias in lower:
            return canonical
    return raw_name.strip() or "Unknown"


def normalize_iata(code: str) -> Optional[str]:
    """Return uppercase IATA code if valid, else None."""
    code = code.strip().upper()
    return code if code in AIRPORTS else None


def parse_time_str(time_str: str) -> Optional[time]:
    """Parse 'HH:MM' or 'HH:MM:SS' to a time object."""
    if not time_str:
        return None
    try:
        parts = time_str.strip().split(":")
        h, m = int(parts[0]), int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        return time(hour=h % 24, minute=m % 60, second=s % 60)
    except Exception:
        return None


def parse_duration(duration_str: str | int) -> int:
    """
    Parse duration to minutes.
    Accepts: int (already minutes), '2h 30m', '2:30', 150, etc.
    """
    if isinstance(duration_str, (int, float)):
        return int(duration_str)
    s = str(duration_str).strip().lower()
    if not s:
        return 0

    # Format: '2h 30m' or '2h30m'
    import re
    h_m = re.match(r"(\d+)h\s*(\d+)m?", s)
    if h_m:
        return int(h_m.group(1)) * 60 + int(h_m.group(2))
    # Format: '2h'
    h_only = re.match(r"(\d+)h", s)
    if h_only:
        return int(h_only.group(1)) * 60
    # Format: '150' or '150m'
    m_only = re.match(r"(\d+)m?", s)
    if m_only:
        return int(m_only.group(1))
    return 0


def compute_advance_days(scrape_date: date, travel_date: date) -> int:
    """Return number of days between scrape date and travel date."""
    delta = travel_date - scrape_date
    return max(0, delta.days)


# ── FareRecord → DB-ready dict ────────────────────────────────────────────────
def normalize_fare_record(
    record: FareRecord,
    source_portal: str,
    scrape_date: Optional[date] = None,
) -> Optional[dict]:
    """
    Convert a raw FareRecord into a DB-ready dict.
    Returns None if the record is invalid.
    """
    scrape_date = scrape_date or datetime.now(tz=timezone.utc).date()

    # Validate IATA
    origin = normalize_iata(record.origin)
    destination = normalize_iata(record.destination)
    if not origin:
        logger.debug("Invalid origin IATA: {}", record.origin)
        return None
    if not destination:
        logger.debug("Invalid destination IATA: {}", record.destination)
        return None

    # Fare sanity
    total_fare = float(record.total_fare or 0)
    if total_fare <= 0:
        logger.debug("Zero/negative total fare — skipping: {}", record)
        return None
    if total_fare > 500_000:
        logger.debug("Suspiciously high fare (>{}) — skipping: {}", 500_000, record)
        return None

    base_fare = float(record.base_fare or 0)
    taxes_fees = float(record.taxes_fees or 0)

    # If base+taxes provided but don't add up to total, recalculate taxes
    if base_fare > 0 and taxes_fees == 0:
        taxes_fees = total_fare - base_fare
    elif base_fare == 0 and taxes_fees == 0:
        # Only total known — leave base/taxes as 0
        pass

    return {
        "scraped_at": datetime.now(tz=timezone.utc),
        "travel_date": record.travel_date,
        "origin": origin,
        "destination": destination,
        "airline": normalize_airline_name(record.airline, record.airline_code),
        "airline_code": record.airline_code.upper() if record.airline_code else None,
        "flight_number": record.flight_number or None,
        "departure_time": parse_time_str(record.departure_time),
        "arrival_time": parse_time_str(record.arrival_time),
        "duration_minutes": parse_duration(record.duration_minutes) or None,
        "stops": max(0, int(record.stops or 0)),
        "fare_class": record.fare_class or "Economy",
        "base_fare": base_fare or None,
        "taxes_fees": taxes_fees or None,
        "total_fare": total_fare,
        "currency": record.currency or "INR",
        "seats_left": int(record.seats_left or 0) or None,
        "source_portal": source_portal,
        "advance_days": compute_advance_days(scrape_date, record.travel_date),
        "is_refundable": record.is_refundable,
        "is_outlier": False,  # Set by outlier detection below
        "raw_json": str(record.raw) if record.raw else None,
    }


# ── Batch normalization + deduplication ──────────────────────────────────────
def normalize_batch(
    records: list[FareRecord],
    source_portal: str,
    scrape_date: Optional[date] = None,
) -> list[dict]:
    """
    Normalize a list of FareRecords:
      1. Convert each to DB dict (filter invalids)
      2. Deduplicate: same flight_number + dep_time → keep cheapest
      3. Flag outliers within the batch
    """
    normalized = []
    for record in records:
        data = normalize_fare_record(record, source_portal, scrape_date)
        if data:
            normalized.append(data)

    # Deduplication
    deduplicated = _deduplicate(normalized)

    # Outlier detection (within this batch)
    deduplicated = _flag_outliers(deduplicated)

    logger.info(
        "[normalizer] {} raw → {} valid → {} after dedup",
        len(records), len(normalized), len(deduplicated),
    )
    return deduplicated


def _deduplicate(records: list[dict]) -> list[dict]:
    """
    Keep cheapest record per unique (flight_number, departure_time).
    For records without a flight_number, use (airline, departure_time).
    """
    seen: dict[tuple, dict] = {}
    for rec in records:
        key = (
            rec.get("flight_number") or rec.get("airline"),
            str(rec.get("departure_time") or ""),
            str(rec.get("fare_class") or ""),
        )
        if key not in seen or rec["total_fare"] < seen[key]["total_fare"]:
            seen[key] = rec
    return list(seen.values())


def _flag_outliers(records: list[dict]) -> list[dict]:
    """
    Flag records whose total_fare is more than 3 standard deviations
    from the batch mean as outliers.
    """
    if len(records) < 5:
        return records  # Not enough data for meaningful stats

    fares = [r["total_fare"] for r in records]
    mean = statistics.mean(fares)
    stdev = statistics.stdev(fares)

    if stdev == 0:
        return records

    for rec in records:
        z_score = abs(rec["total_fare"] - mean) / stdev
        rec["is_outlier"] = z_score > 3.0

    outlier_count = sum(1 for r in records if r["is_outlier"])
    if outlier_count:
        logger.warning("[normalizer] {} outliers flagged in batch", outlier_count)

    return records
