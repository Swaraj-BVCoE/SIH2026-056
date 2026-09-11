from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import mean
from typing import Iterable, Mapping


def percentage_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / previous * 100, 2)


def calculate_index_series(observations: Iterable[Mapping], weights: Mapping[str, float]) -> list[dict]:
    """Calculate weighted route price relatives using the first route/day as base."""
    rows = sorted(observations, key=lambda row: (row["date"], row["route"]))
    bases: dict[str, float] = {}
    by_date: dict[date, list[Mapping]] = defaultdict(list)
    for row in rows:
        fare = float(row["avg_fare"] or 0)
        if fare <= 0:
            continue
        bases.setdefault(row["route"], fare)
        by_date[row["date"]].append(row)
    series: list[dict] = []
    for observed_date, day_rows in sorted(by_date.items()):
        usable = [row for row in day_rows if row["route"] in weights and bases.get(row["route"])]
        weight_total = sum(weights[row["route"]] for row in usable)
        if not usable or weight_total <= 0:
            continue
        value = 0.0
        for row in usable:
            relative = float(row["avg_fare"]) / bases[row["route"]] * 100
            value += relative * weights[row["route"]] / weight_total
        series.append({
            "date": observed_date,
            "value": round(value, 2),
            "routes_used": len(usable),
            "records_used": sum(int(row.get("count", 0) or 0) for row in usable),
        })
    return series


def aggregate_frequency(series: list[dict], frequency: str) -> list[dict]:
    if frequency == "daily":
        return series
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for item in series:
        d = item["date"]
        key = (d.year, d.isocalendar().week) if frequency == "weekly" else (d.year, d.month)
        buckets[key].append(item)
    result = []
    for items in buckets.values():
        result.append({
            "date": max(item["date"] for item in items),
            "value": round(mean(item["value"] for item in items), 2),
            "routes_used": max(item["routes_used"] for item in items),
            "records_used": sum(item["records_used"] for item in items),
        })
    return sorted(result, key=lambda item: item["date"])


def value_on_or_before(series: list[dict], target: date) -> float | None:
    eligible = [item for item in series if item["date"] <= target]
    return eligible[-1]["value"] if eligible else None
