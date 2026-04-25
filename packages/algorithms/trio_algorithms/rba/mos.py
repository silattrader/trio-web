"""MOS (Margin-of-Safety) Graham liquid-value model.

SOP: docs/algorithms/mos.md
Ported from: https://github.com/shah05/trio-mvp/blob/master/app/mos.py
"""
from __future__ import annotations

from typing import Any

from .._common import assign_quartiles, coerce_float
from ..contracts import (
    QUARTILE_TO_RECOMMENDATION,
    FactorBreakdown,
    Recommendation,
    ScoreResponse,
    StockResult,
)

MODEL_VERSION = "rba-mos-1.0.0"

BS_FIELDS = (
    "cash_near_cash",
    "accounts_receivable",
    "inventories",
    "other_current_assets",
    "accounts_payable",
    "other_st_liab",
    "st_borrow",
    "non_current_liab",
    "shares_out",
    "px_last",
    "best_target_price",
)


def _liquid_value(r: dict[str, float]) -> float:
    return (
        r["cash_near_cash"]
        + 0.75 * r["accounts_receivable"]
        + 0.75 * r["inventories"]
        + r["other_current_assets"]
        - (r["accounts_payable"] + r["other_st_liab"] + r["st_borrow"] + r["non_current_liab"])
    )


def score_mos(rows: list[dict[str, Any]], *, universe: str = "CSV") -> ScoreResponse:
    results: list[StockResult] = []
    magic_nos: list[float | None] = []

    for row in rows:
        clean: dict[str, float | None] = {f: coerce_float(row.get(f)) for f in BS_FIELDS}
        flags: list[str] = []
        breakdowns: list[FactorBreakdown] = []
        magic_no: float | None = None

        if any(clean[f] is None for f in BS_FIELDS):
            flags.append("missing_balance_sheet")
        elif clean["shares_out"] in (0, None):
            flags.append("bad_shares_out")
        else:
            r = {f: clean[f] for f in BS_FIELDS}  # type: ignore[misc]
            lv = _liquid_value(r)  # type: ignore[arg-type]
            lv_per_sh = lv / r["shares_out"]
            a_premium = 1.0 - (lv_per_sh / r["px_last"]) if r["px_last"] else None
            b_upside = (
                (r["best_target_price"] - r["px_last"]) / r["px_last"] if r["px_last"] else None
            )

            if b_upside is None or b_upside <= 0:
                flags.append("no_upside")
            elif a_premium is None:
                flags.append("bad_px_last")
            else:
                magic_no = a_premium / b_upside

            for fid, label, val in [
                ("M1", "Liquid Value", lv),
                ("M2", "Liquid Value / Share", lv_per_sh),
                ("M3", "A — Premium %", (a_premium or 0) * 100),
                ("M4", "B — Target Upside %", (b_upside or 0) * 100),
                ("M5", "Magic No (A/B)", magic_no if magic_no is not None else float("nan")),
            ]:
                breakdowns.append(
                    FactorBreakdown(
                        id=fid, label=label, raw=val,
                        band="N/A", sub_score=0, weight=0, contribution=0,
                    )
                )

        magic_nos.append(magic_no)
        results.append(
            StockResult(
                ticker=str(row.get("ticker") or row.get("KLCI_INDEX_NAME") or "?"),
                name=row.get("name") or row.get("LONG_COMP_NAME"),
                final_score=magic_no,
                quartile=None,
                recommendation=Recommendation.UNRANKED,
                factors=breakdowns,
                explanation=_explain(breakdowns, magic_no, flags),
                flags=flags,
            )
        )

    # MOS: lower magic_no is better -> ascending=True so Q1 = lowest.
    quartiles = assign_quartiles(magic_nos, ascending=True)
    for r, q in zip(results, quartiles):
        r.quartile = q
        if q is not None:
            r.recommendation = QUARTILE_TO_RECOMMENDATION[q]

    n_scored = sum(1 for s in magic_nos if s is not None)
    warnings: list[str] = []
    if n_scored < 4:
        warnings.append(f"Only {n_scored} rows had valid magic numbers; quartiles not assigned.")

    return ScoreResponse(
        model_version=MODEL_VERSION,
        universe=universe,
        n_rows=len(rows),
        n_scored=n_scored,
        results=results,
        warnings=warnings,
    )


def _explain(breakdowns, magic_no, flags) -> str:
    if magic_no is None:
        return f"Excluded from ranking ({', '.join(flags) or 'unknown'})."
    a = next((b for b in breakdowns if b.id == "M3"), None)
    bup = next((b for b in breakdowns if b.id == "M4"), None)
    if a is None or bup is None:
        return f"Magic No = {magic_no:.2f}."
    return (
        f"Trades at {a.raw:.1f}% premium to liquid value with {bup.raw:.1f}% analyst upside "
        f"(Magic No {magic_no:.2f} — lower is better)."
    )
