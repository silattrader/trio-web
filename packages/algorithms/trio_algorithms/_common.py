"""Shared helpers: data cleaning, quartile assignment, NaN-safe coercion."""
from __future__ import annotations

import math
from typing import Any

NA_TOKENS = {
    "#N/A Field Not Applicable",
    "#N/A N/A",
    "#N/A Invalid Security",
    "-",
    "#VALUE!",
    "",
    "nan",
    "NaN",
}


def coerce_float(value: Any) -> float | None:
    """Best-effort float coercion. Returns None for NaN / NA tokens / un-parseable strings."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "").replace("%", "")
        if s in NA_TOKENS:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def assign_quartiles(scores: list[float | None], *, ascending: bool = False) -> list[int | None]:
    """Assign quartiles 1..4 where 1 is best.

    ascending=False (default): highest score -> Q1 (BOS, four-factor).
    ascending=True: lowest score -> Q1 (MOS magic_no).

    Rows with score=None get quartile=None. Universes < 4 ranked rows return all None.
    """
    indexed = [(i, s) for i, s in enumerate(scores) if s is not None and not math.isnan(s)]
    if len(indexed) < 4:
        return [None] * len(scores)

    indexed.sort(key=lambda t: t[1], reverse=not ascending)
    n = len(indexed)
    out: list[int | None] = [None] * len(scores)
    for rank, (orig_idx, _) in enumerate(indexed):
        # rank 0..n-1; top 25% -> Q1
        q = min(4, rank * 4 // n + 1)
        out[orig_idx] = q
    return out


def band_from_thresholds(
    value: float | None, *, buy_above: float, sell_below: float
) -> tuple[str, float]:
    """Three-band scoring with sub_score in {3, 2, 1}. Returns (band, sub_score).

    NaN/None -> ("N/A", 0).
    """
    if value is None or math.isnan(value):
        return "N/A", 0.0
    if value > buy_above:
        return "BUY", 3.0
    if value < sell_below:
        return "SELL", 1.0
    return "NEUTRAL", 2.0
