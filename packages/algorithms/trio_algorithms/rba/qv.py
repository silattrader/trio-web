"""QV — Quality-Value 6-factor screen.

Inspired by three landmark factor-investing strategies:

  · Greenblatt's *Magic Formula* (2006) — earnings yield (EBIT/EV) as the
    cleanest single-factor value signal.
  · Novy-Marx's *Gross Profitability* (2013) — gross profit / total assets
    as the strongest single-factor quality signal in academic backtests.
  · Graham's safety-of-principal — leverage (debt/equity) as a downside hedge.

Six factors split half quality, half value. All factors land on the BOS
banding scale (SELL=1, NEUTRAL=2, BUY=3 sub_score; weighted sum gives final
score in [1, 3], quartiles assigned identically to BOS).

Field-name conventions on canonical row dicts:
    roe                       — return on equity (%)
    gross_profit_to_assets    — gross profit / total assets (ratio)
    debt_to_equity            — total debt / equity (ratio, lower better)
    earnings_yield            — EBIT / market cap (% — Greenblatt formulation)
    book_to_market            — book value / market cap (ratio)
    fcf_yield                 — free cash flow / market cap (%)

SOP: docs/algorithms/qv.md
"""
from __future__ import annotations

from typing import Any

from .._common import assign_quartiles, band_from_thresholds, coerce_float
from ..contracts import (
    QUARTILE_TO_RECOMMENDATION,
    FactorBreakdown,
    QvWeights,
    Recommendation,
    ScoreResponse,
    StockResult,
)

MODEL_VERSION = "rba-qv-1.0.0"


def _band_reversed(
    value: float | None, *, buy_below: float, sell_above: float
) -> tuple[str, float]:
    """Three-band scoring where LOWER is better (e.g. debt/equity).

    Returns (band, sub_score) on the same {1, 2, 3} scale as
    `band_from_thresholds` so contributions stay comparable.
    """
    import math
    if value is None or math.isnan(value):
        return "N/A", 0.0
    if value < buy_below:
        return "BUY", 3.0
    if value > sell_above:
        return "SELL", 1.0
    return "NEUTRAL", 2.0


# Factor definitions: (id, label, source_field, default_weight, buy, sell, weights_attr, reversed)
# `reversed=True` means LOWER values are better (debt/equity).
FACTORS: list[tuple[str, str, str, float, float, float, str, bool]] = [
    # Quality (50%)
    ("F1", "Return on Equity %",      "roe",                    0.15, 15.0, 5.0,  "f1_roe",                    False),
    ("F2", "Gross Profit / Assets",   "gross_profit_to_assets", 0.20, 0.30, 0.10, "f2_gross_profit_to_assets", False),
    ("F3", "Debt / Equity",           "debt_to_equity",         0.15, 0.5,  1.5,  "f3_debt_to_equity",         True),
    # Value (50%)
    ("F4", "Earnings Yield % (EBIT/EV)", "earnings_yield",      0.20, 8.0,  2.0,  "f4_earnings_yield",         False),
    ("F5", "Book / Market",           "book_to_market",         0.15, 0.6,  0.2,  "f5_book_to_market",         False),
    ("F6", "FCF Yield %",             "fcf_yield",              0.15, 6.0,  2.0,  "f6_fcf_yield",              False),
]


def score_qv(
    rows: list[dict[str, Any]],
    *,
    universe: str = "CSV",
    weights: QvWeights | None = None,
) -> ScoreResponse:
    """Score the universe with the 6-factor Quality-Value engine.

    Same return contract as `score_bos` (`ScoreResponse`); UI never branches
    on engine type.
    """
    results: list[StockResult] = []
    raw_scores: list[float | None] = []

    effective = (weights.normalised() if weights else QvWeights())
    weights_warning: list[str] = []
    if weights and weights != QvWeights():
        weights_warning.append(
            "QV weights overridden from canonical "
            f"({_w_csv(QvWeights())}) to {_w_csv(effective)}."
        )

    for row in rows:
        breakdowns: list[FactorBreakdown] = []
        final_score = 0.0
        any_value = False

        for fid, label, field, _default, buy, sell, attr, is_reversed in FACTORS:
            weight = getattr(effective, attr)
            raw = coerce_float(row.get(field))
            if is_reversed:
                band, sub = _band_reversed(raw, buy_below=buy, sell_above=sell)
            else:
                band, sub = band_from_thresholds(raw, buy_above=buy, sell_below=sell)
            contribution = sub * weight
            final_score += contribution
            if raw is not None:
                any_value = True
            breakdowns.append(FactorBreakdown(
                id=fid, label=label, raw=raw, band=band,
                sub_score=sub, weight=weight, contribution=contribution,
                flags=["missing"] if raw is None else [],
            ))

        score = final_score if any_value else None
        raw_scores.append(score)
        results.append(StockResult(
            ticker=str(row.get("ticker") or row.get("KLCI_INDEX_NAME") or "?"),
            name=row.get("name") or row.get("LONG_COMP_NAME"),
            final_score=score, quartile=None,
            recommendation=Recommendation.UNRANKED,
            factors=breakdowns,
            explanation=_explain(breakdowns, score),
        ))

    quartiles = assign_quartiles(raw_scores, ascending=False)
    for r, q in zip(results, quartiles):
        r.quartile = q
        if q is not None:
            r.recommendation = QUARTILE_TO_RECOMMENDATION[q]

    n_scored = sum(1 for s in raw_scores if s is not None)
    warnings: list[str] = list(weights_warning)
    if n_scored < 4:
        warnings.append(f"Universe has only {n_scored} scorable rows; quartiles not assigned.")

    return ScoreResponse(
        model_version=MODEL_VERSION,
        universe=universe,
        n_rows=len(rows),
        n_scored=n_scored,
        results=results,
        warnings=warnings,
    )


def _w_csv(w: QvWeights) -> str:
    return (
        f"roe={w.f1_roe:.2f}, gp/a={w.f2_gross_profit_to_assets:.2f}, "
        f"d/e={w.f3_debt_to_equity:.2f}, ey={w.f4_earnings_yield:.2f}, "
        f"b/m={w.f5_book_to_market:.2f}, fcf={w.f6_fcf_yield:.2f}"
    )


def _explain(breakdowns: list[FactorBreakdown], score: float | None) -> str:
    if score is None:
        return "Insufficient data — no factors available."
    top = sorted(breakdowns, key=lambda b: b.contribution, reverse=True)[:2]
    bot = sorted(breakdowns, key=lambda b: b.contribution)[:1]
    parts = [
        f"{b.label} {b.band.lower()}"
        + (f" ({b.raw:.2f})" if b.raw is not None else "")
        for b in top if b.band != "N/A"
    ]
    drag = [
        f"weighed down by {b.label} {b.band.lower()}"
        for b in bot if b.raw is not None and b.band == "SELL"
    ]
    return "Strongest signals: " + ", ".join(parts) + ("; " + "; ".join(drag) if drag else "") + "."
