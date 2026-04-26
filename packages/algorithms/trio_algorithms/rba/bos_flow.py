"""BOS-Flow — 7-factor weighted score (BOS + insider + retail flow).

Extends classical BOS with two flow-pressure factors:
- F6 ``insider_flow`` — Form 4 net insider buying, score 1-5 (5 = strong BUY)
- F7 ``retail_flow`` — Wikipedia attention z-score, score 1-5 (5 = BUY,
  but contrarian: 5 only when attention is at/below baseline; spikes → 1-2)

The first 5 factors retain BOS's banding (raw value → BUY/NEUTRAL/SELL via
threshold). F6 and F7 arrive *already scored* on the 1-5 scale from their
respective providers, so we map their integer score back to a band for the
factor-breakdown UI but keep the score itself as-is.

SOP: docs/algorithms/bos_flow.md (this is the public-demo default model).
"""
from __future__ import annotations

from typing import Any

from .._common import assign_quartiles, band_from_thresholds, coerce_float
from ..contracts import (
    QUARTILE_TO_RECOMMENDATION,
    BosFlowWeights,
    FactorBreakdown,
    Recommendation,
    ScoreResponse,
    StockResult,
)

MODEL_VERSION = "rba-bos-flow-1.0.0"

# Same threshold logic as BOS for the original 5 factors.
THRESHOLD_FACTORS = [
    # (id, label, source_field, default_weight, buy_above, sell_below, weights_attr)
    ("F1", "Volume Avg 3M",      "vol_avg_3m",    0.15, 440_000.0, 300_000.0, "f1_volume"),
    ("F2", "Target Return %",    "target_return", 0.15, 15.0,      -15.0,     "f2_target"),
    ("F3", "Dividend Yield %",   "dvd_yld_ind",   0.15, 6.0,       3.5,       "f3_dvd_yld"),
    ("F4", "Altman Z-Score",     "altman_z",      0.20, 2.0,       1.5,       "f4_altman_z"),
    ("F5", "Analyst Sentiment",  "analyst_sent",  0.10, 4.2,       3.0,       "f5_analyst_sent"),
]

# Pre-scored factors (1-5) from upstream providers.
PRESCORED_FACTORS = [
    # (id, label, source_field, default_weight, weights_attr)
    ("F6", "Insider Flow",  "insider_flow", 0.15, "f6_insider_flow"),
    ("F7", "Retail Flow",   "retail_flow",  0.10, "f7_retail_flow"),
]


def _band_from_prescored(score: float) -> str:
    """Map a 1-5 prescored factor back to a BUY/NEUTRAL/SELL band for display."""
    if score >= 4.0:
        return "BUY"
    if score >= 2.5:
        return "NEUTRAL"
    if score >= 1.0:
        return "SELL"
    return "N/A"


def score_bos_flow(
    rows: list[dict[str, Any]],
    *,
    universe: str = "CSV",
    weights: BosFlowWeights | None = None,
) -> ScoreResponse:
    """Score the universe using the 7-factor BOS-Flow engine.

    Both threshold-banded factors (F1-F5) and prescored factors (F6-F7)
    contribute to the final weighted sum. Each factor's sub_score is on
    the same 1-5 scale (BUY=4 in BOS bands; pre-scored values pass through).

    Wait — BOS uses sub_score 0-3 (SELL=1, NEUTRAL=2, BUY=3). Match that.
    """
    results: list[StockResult] = []
    raw_scores: list[float | None] = []

    effective = (weights.normalised() if weights else BosFlowWeights())
    weights_warning: list[str] = []
    if weights and weights != BosFlowWeights():
        weights_warning.append(
            "BOS-Flow weights overridden from canonical "
            f"({_w_csv(BosFlowWeights())}) to {_w_csv(effective)}."
        )

    for row in rows:
        breakdowns: list[FactorBreakdown] = []
        final_score = 0.0
        any_value = False

        # F1-F5: classic BOS banding.
        for fid, label, field, _default, buy, sell, attr in THRESHOLD_FACTORS:
            weight = getattr(effective, attr)
            raw = coerce_float(row.get(field))
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

        # F6-F7: prescored 1-5 → convert to BOS sub_score scale (1=SELL → 1,
        # 3=NEUTRAL → 2, 5=BUY → 3) using a linear map: sub = (score - 1) / 2.
        for fid, label, field, _default, attr in PRESCORED_FACTORS:
            weight = getattr(effective, attr)
            raw = coerce_float(row.get(field))
            if raw is None:
                breakdowns.append(FactorBreakdown(
                    id=fid, label=label, raw=None, band="N/A",
                    sub_score=0.0, weight=weight, contribution=0.0,
                    flags=["missing"],
                ))
                continue
            # Clamp to [1, 5] then map to [0, 3].
            s = max(1.0, min(5.0, raw))
            sub = (s - 1.0) / 2.0  # 1 → 0, 3 → 1, 5 → 2; tweak below
            # Match BOS: SELL=1, NEUTRAL=2, BUY=3 (so 5-scale 1→1, 3→2, 5→3).
            # Use linear: sub = 1 + (s - 1) * 0.5  → 1→1, 3→2, 5→3
            sub = 1.0 + (s - 1.0) * 0.5
            contribution = sub * weight
            final_score += contribution
            any_value = True
            breakdowns.append(FactorBreakdown(
                id=fid, label=label, raw=raw, band=_band_from_prescored(s),
                sub_score=sub, weight=weight, contribution=contribution, flags=[],
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


def _w_csv(w: BosFlowWeights) -> str:
    return (
        f"vol={w.f1_volume:.2f}, tgt={w.f2_target:.2f}, "
        f"dvd={w.f3_dvd_yld:.2f}, altz={w.f4_altman_z:.2f}, "
        f"sent={w.f5_analyst_sent:.2f}, ins={w.f6_insider_flow:.2f}, "
        f"ret={w.f7_retail_flow:.2f}"
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
