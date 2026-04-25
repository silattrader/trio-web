"""BOS (Buy-Or-Sell) 5-factor weighted score.

SOP: docs/algorithms/bos.md
Ported from: https://github.com/shah05/trio-mvp/blob/master/app/bos.py
"""
from __future__ import annotations

from typing import Any

from .._common import assign_quartiles, band_from_thresholds, coerce_float
from ..contracts import (
    QUARTILE_TO_RECOMMENDATION,
    BosWeights,
    FactorBreakdown,
    Recommendation,
    ScoreResponse,
    StockResult,
)

MODEL_VERSION = "rba-bos-1.0.0"

# Canonical 5 factors. Weights are CANONICAL defaults; can be overridden per-call
# via score_bos(..., weights=BosWeights(...)).
FACTORS = [
    # (id, label, source_field, default_weight, buy_above, sell_below, weights_attr)
    ("F1", "Volume Avg 3M",      "vol_avg_3m",    0.20, 440_000.0, 300_000.0, "f1_volume"),
    ("F2", "Target Return %",    "target_return", 0.20, 15.0,      -15.0,     "f2_target"),
    ("F3", "Dividend Yield %",   "dvd_yld_ind",   0.20, 6.0,       3.5,       "f3_dvd_yld"),
    ("F4", "Altman Z-Score",     "altman_z",      0.30, 2.0,       1.5,       "f4_altman_z"),
    ("F5", "Analyst Sentiment",  "analyst_sent",  0.10, 4.2,       3.0,       "f5_analyst_sent"),
]


def score_bos(
    rows: list[dict[str, Any]],
    *,
    universe: str = "CSV",
    weights: BosWeights | None = None,
) -> ScoreResponse:
    results: list[StockResult] = []
    raw_scores: list[float | None] = []

    effective = (weights.normalised() if weights else BosWeights())
    weights_warning: list[str] = []
    if weights and weights != BosWeights():
        weights_warning.append(
            "BOS weights overridden from canonical "
            f"({_w_csv(BosWeights())}) to {_w_csv(effective)}."
        )

    for row in rows:
        breakdowns: list[FactorBreakdown] = []
        final_score = 0.0
        any_value = False

        for fid, label, field, _default, buy, sell, attr in FACTORS:
            weight = getattr(effective, attr)
            raw = coerce_float(row.get(field))
            band, sub = band_from_thresholds(raw, buy_above=buy, sell_below=sell)
            contribution = sub * weight
            final_score += contribution
            if raw is not None:
                any_value = True
            breakdowns.append(
                FactorBreakdown(
                    id=fid,
                    label=label,
                    raw=raw,
                    band=band,
                    sub_score=sub,
                    weight=weight,
                    contribution=contribution,
                    flags=["missing"] if raw is None else [],
                )
            )

        score = final_score if any_value else None
        raw_scores.append(score)
        results.append(
            StockResult(
                ticker=str(row.get("ticker") or row.get("KLCI_INDEX_NAME") or "?"),
                name=row.get("name") or row.get("LONG_COMP_NAME"),
                final_score=score,
                quartile=None,
                recommendation=Recommendation.UNRANKED,
                factors=breakdowns,
                explanation=_explain(breakdowns, score),
            )
        )

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


def _w_csv(w: BosWeights) -> str:
    return (
        f"vol={w.f1_volume:.2f}, tgt={w.f2_target:.2f}, "
        f"dvd={w.f3_dvd_yld:.2f}, altz={w.f4_altman_z:.2f}, "
        f"sent={w.f5_analyst_sent:.2f}"
    )


def _explain(breakdowns: list[FactorBreakdown], score: float | None) -> str:
    if score is None:
        return "Insufficient data — no factors available."
    top = sorted(breakdowns, key=lambda b: b.contribution, reverse=True)[:2]
    bot = sorted(breakdowns, key=lambda b: b.contribution)[:1]
    parts = [f"{b.label} {b.band.lower()} ({b.raw:.2f})" for b in top if b.raw is not None]
    drag = [f"weighed down by {b.label} {b.band.lower()}" for b in bot if b.raw is not None and b.band == "SELL"]
    return "Strongest signals: " + ", ".join(parts) + ("; " + "; ".join(drag) if drag else "") + "."
