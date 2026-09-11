from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IndexLatestResponse(BaseModel):
    value: float | None = Field(None, description="Latest weighted APIx value; null when no valid observations exist")
    daily_change: float | None = None
    weekly_change: float | None = None
    monthly_change: float | None = None
    base_period: str
    last_updated: datetime | None = None
    routes_used: int
    records_used: int
    freshness: dict[str, Any]
    weights: dict[str, Any]
