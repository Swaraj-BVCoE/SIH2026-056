"""
pipeline/validator.py
──────────────────────
Pydantic schema validation for normalized fare dicts before DB write.
Ensures data integrity — no corrupt records enter the database.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator


class FlightPriceSchema(BaseModel):
    """
    Validated schema for a flight price record.
    Matches the FlightPrice SQLAlchemy model.
    """

    # Required fields
    scraped_at: datetime
    travel_date: date
    origin: str = Field(min_length=3, max_length=3)
    destination: str = Field(min_length=3, max_length=3)
    airline: str = Field(min_length=1, max_length=64)
    total_fare: float = Field(gt=0)
    source_portal: str = Field(min_length=1, max_length=32)
    advance_days: int = Field(ge=0)

    # Optional fields
    airline_code: Optional[str] = Field(None, max_length=4)
    flight_number: Optional[str] = Field(None, max_length=10)
    departure_time: Optional[time] = None
    arrival_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(None, ge=0)
    stops: int = Field(default=0, ge=0, le=10)
    fare_class: str = Field(default="Economy", max_length=32)
    base_fare: Optional[float] = Field(None, ge=0)
    taxes_fees: Optional[float] = Field(None, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    seats_left: Optional[int] = Field(None, ge=0)
    is_outlier: bool = False
    is_refundable: Optional[bool] = None
    raw_json: Optional[str] = None
    scrape_run_id: Optional[int] = None

    @field_validator("origin", "destination", mode="before")
    @classmethod
    def uppercase_iata(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("currency", mode="before")
    @classmethod
    def uppercase_currency(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("total_fare", "base_fare", "taxes_fees", mode="before")
    @classmethod
    def parse_float(cls, v) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(str(v).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    @model_validator(mode="after")
    def check_route_not_same(self) -> "FlightPriceSchema":
        if self.origin == self.destination:
            raise ValueError(f"Origin and destination are the same: {self.origin}")
        return self

    @model_validator(mode="after")
    def check_fare_consistency(self) -> "FlightPriceSchema":
        """Base fare + taxes should roughly equal total fare (within 5% tolerance)."""
        if self.base_fare and self.taxes_fees:
            computed = self.base_fare + self.taxes_fees
            diff = abs(computed - self.total_fare)
            if diff > self.total_fare * 0.05:  # 5% tolerance
                # Auto-correct taxes
                self.taxes_fees = self.total_fare - self.base_fare
        return self

    class Config:
        arbitrary_types_allowed = True


def validate_record(record_dict: dict) -> Optional[FlightPriceSchema]:
    """
    Validate a normalized dict. Returns a FlightPriceSchema on success,
    or None (with a warning log) on validation failure.
    """
    try:
        return FlightPriceSchema(**record_dict)
    except Exception as exc:
        logger.warning(
            "[validator] Record failed validation: {} | Data: {}",
            exc,
            {k: v for k, v in record_dict.items() if k != "raw_json"},
        )
        return None


def validate_batch(records: list[dict]) -> tuple[list[FlightPriceSchema], int]:
    """
    Validate a batch of normalized dicts.

    Returns:
        (valid_records, invalid_count)
    """
    valid: list[FlightPriceSchema] = []
    invalid = 0

    for rec in records:
        schema = validate_record(rec)
        if schema:
            valid.append(schema)
        else:
            invalid += 1

    if invalid:
        logger.warning(
            "[validator] {}/{} records failed validation",
            invalid, len(records),
        )

    return valid, invalid
