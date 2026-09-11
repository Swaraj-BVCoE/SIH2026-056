"""Configurable airfare price-index calculation package."""

from .calculator import calculate_index_series, percentage_change
from .weights import load_weights

__all__ = ["calculate_index_series", "percentage_change", "load_weights"]
