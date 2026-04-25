"""4-Factor legacy model (TRIO 2019 formulation).

SOP: docs/algorithms/four_factor.md
Ported from: https://github.com/shah05/trio-mvp/blob/master/app/main.py

Legacy `main.py` accidentally excluded F3 from the total score. We expose:
- `score_four_factor(rows, legacy=False)` -> corrected (F1+F2+F3+F4), default
- `score_four_factor(rows, legacy=True)`  -> bug-for-bug (F1+F2+F4 only)
"""
from __future__ import annotations

import statistics
from typing import Any

from .._common import assign_quartiles, coerce_float
from ..contracts import (
    QUARTILE_TO_RECOMMENDATION,
    FactorBreakdown,
    Recommendation,
    ScoreResponse,
    StockResult,
)

MODEL_VERSION_CORRECTED = "rba-four-factor-1.0.0"
MODEL_VERSION_LEGACY = "rba-four-factor-legacy-1.0.0"


def _f1_altman(z: float | None) -> tuple[str, float]:
    if z is None:
        return "N/A", 0.0
    if z > 2:
        return "BUY", 1.0
    if z < 1:
        return "SELL", 0.0
    return "NEUTRAL", 0.25


def _f2_dvd(yld: float | None, mean: float) -> tuple[str, float]:
    if yld is None:
        return "N/A", 0.0
    return ("BUY", 1.0) if yld > mean else ("SELL", 0.5)


def _f3_roe(roe: float | None, q25: float, q50: float, q75: float) -> tuple[str, float]:
    if roe is None:
        return "N/A", 0.0
    if roe > q75:
        return "BUY", 1.0
    if roe > q50:
        return "BUY", 0.75
    if roe > q25:
        return "NEUTRAL", 0.5
    return "SELL", 0.0


def _f4_pe(curr: float | None, avg5: float | None) -> tuple[str, float]:
    if curr is None or avg5 is None:
        return "N/A", 0.0
    return ("BUY", 1.0) if curr < avg5 else ("SELL", 0.0)


def score_four_factor(
    rows: list[dict[str, Any]], *, universe: str = "CSV", legacy: bool = False
) -> ScoreResponse:
    # Universe-relative parameters
    dvd_yields = [v for v in (coerce_float(r.get("dvd_yld_est")) for r in rows) if v is not None]
    roes = [v for v in (coerce_float(r.get("roe_3yr_avg")) for r in rows) if v is not None]
    dvd_mean = statistics.mean(dvd_yields) if dvd_yields else 0.0
    if len(roes) >= 4:
        sorted_roes = sorted(roes)
        n = len(sorted_roes)
        q25 = sorted_roes[n // 4]
        q50 = sorted_roes[n // 2]
        q75 = sorted_roes[(3 * n) // 4]
    else:
        q25 = q50 = q75 = 0.0

    results: list[StockResult] = []
    totals: list[float | None] = []

    for row in rows:
        z = coerce_float(row.get("altman_z"))
        yld = coerce_float(row.get("dvd_yld_est"))
        roe = coerce_float(row.get("roe_3yr_avg"))
        pe_curr = coerce_float(row.get("pe_ratio"))
        pe_avg = coerce_float(row.get("pe_5yr_avg"))

        b1, s1 = _f1_altman(z)
        b2, s2 = _f2_dvd(yld, dvd_mean)
        b3, s3 = _f3_roe(roe, q25, q50, q75)
        b4, s4 = _f4_pe(pe_curr, pe_avg)

        if legacy:
            total = s1 + s2 + s4  # bug preserved
        else:
            total = s1 + s2 + s3 + s4

        any_value = any(v is not None for v in (z, yld, roe, pe_curr))
        score: float | None = total if any_value else None
        totals.append(score)

        breakdowns = [
            FactorBreakdown(
                id="F1", label="Altman Z", raw=z, band=b1,
                sub_score=s1, weight=1.0, contribution=s1,
            ),
            FactorBreakdown(
                id="F2", label="Dvd Yield vs Universe Mean", raw=yld, band=b2,
                sub_score=s2, weight=1.0, contribution=s2,
            ),
            FactorBreakdown(
                id="F3", label="ROE 3yr Avg (quartile)", raw=roe, band=b3,
                sub_score=s3, weight=0.0 if legacy else 1.0,
                contribution=0.0 if legacy else s3,
                flags=["excluded_legacy"] if legacy else [],
            ),
            FactorBreakdown(
                id="F4", label="P/E vs 5yr Avg", raw=pe_curr, band=b4,
                sub_score=s4, weight=1.0, contribution=s4,
            ),
        ]

        results.append(
            StockResult(
                ticker=str(row.get("ticker") or row.get("KLCI_INDEX_NAME") or "?"),
                name=row.get("name") or row.get("LONG_COMP_NAME"),
                final_score=score,
                quartile=None,
                recommendation=Recommendation.UNRANKED,
                factors=breakdowns,
            )
        )

    quartiles = assign_quartiles(totals, ascending=False)
    for r, q in zip(results, quartiles):
        r.quartile = q
        if q is not None:
            r.recommendation = QUARTILE_TO_RECOMMENDATION[q]

    return ScoreResponse(
        model_version=MODEL_VERSION_LEGACY if legacy else MODEL_VERSION_CORRECTED,
        universe=universe,
        n_rows=len(rows),
        n_scored=sum(1 for t in totals if t is not None),
        results=results,
        warnings=[],
    )
