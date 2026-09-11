from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable


def normalize_weights(weights: dict[str, float]) -> tuple[dict[str, float], bool]:
    cleaned = {route.upper(): float(weight) for route, weight in weights.items() if float(weight) > 0}
    total = sum(cleaned.values())
    if not cleaned or total <= 0:
        return {}, False
    changed = abs(total - 1.0) > 1e-6
    return {route: weight / total for route, weight in cleaned.items()}, changed


def load_weights(path: str | Path, routes: Iterable[str]) -> tuple[dict[str, float], dict]:
    """Load weights, falling back to transparent equal weights for observed routes."""
    route_list = sorted(set(route.upper() for route in routes))
    configured: dict[str, float] = {}
    path = Path(path)
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                try:
                    configured[row["route"].strip().upper()] = float(row["weight"])
                except (KeyError, TypeError, ValueError):
                    continue
    usable = {route: configured[route] for route in route_list if configured.get(route, 0) > 0}
    if not usable and route_list:
        usable = {route: 1.0 for route in route_list}
    normalized, changed = normalize_weights(usable)
    return normalized, {
        "label": "DEMO / CONFIGURABLE WEIGHTS",
        "official": False,
        "normalized": changed,
        "configured_routes": len(configured),
        "routes_used": len(normalized),
    }
