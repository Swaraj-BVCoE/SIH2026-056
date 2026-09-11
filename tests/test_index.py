from datetime import date

import pytest

from api.analytics import classify_advance_window
from index.calculator import calculate_index_series, percentage_change
from index.weights import normalize_weights


def test_weight_normalization():
    weights, changed = normalize_weights({"DEL-BOM": 2, "BOM-DEL": 1})
    assert changed is True
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["DEL-BOM"] == pytest.approx(2 / 3)


def test_weighted_route_index():
    rows = [
        {"date": date(2026, 9, 1), "route": "DEL-BOM", "avg_fare": 5000, "count": 4},
        {"date": date(2026, 9, 1), "route": "BOM-DEL", "avg_fare": 4000, "count": 3},
        {"date": date(2026, 9, 2), "route": "DEL-BOM", "avg_fare": 5500, "count": 4},
        {"date": date(2026, 9, 2), "route": "BOM-DEL", "avg_fare": 4000, "count": 3},
    ]
    series = calculate_index_series(rows, {"DEL-BOM": 0.6, "BOM-DEL": 0.4})
    assert series[0]["value"] == 100
    assert series[1]["value"] == 106
    assert series[1]["records_used"] == 7


def test_partial_coverage_renormalizes_weights():
    rows = [
        {"date": date(2026, 9, 1), "route": "DEL-BOM", "avg_fare": 5000},
        {"date": date(2026, 9, 2), "route": "DEL-BOM", "avg_fare": 5500},
    ]
    series = calculate_index_series(rows, {"DEL-BOM": 0.2, "BOM-DEL": 0.8})
    assert series[-1]["value"] == 110


@pytest.mark.parametrize("days,window", [(1, 1), (3, 1), (7, 7), (15, 15), (30, 30), (45, 45), (60, 45), (61, None)])
def test_advance_purchase_classification(days, window):
    assert classify_advance_window(days) == window


def test_percentage_change_handles_empty_base():
    assert percentage_change(110, 100) == 10
    assert percentage_change(110, 0) is None
    assert percentage_change(None, 100) is None
