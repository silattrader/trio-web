"""Promotion gate for MLA → production.

Hard rule from the project memo: MLA cannot ship to users until backtested
return ≥ RBA on the same universe + period. This module formalises that as
a pure function so it can be exercised in tests and surfaced in the UI.

Returns a ``PromotionDecision`` with:

- ``promote``: bool — pass/fail
- ``cagr_lift``: float — MLA CAGR minus RBA CAGR (decimal form)
- ``sharpe_lift``: float — MLA Sharpe minus RBA Sharpe
- ``reasons``: list[str] — every check, pass or fail, with numbers

Default thresholds: CAGR lift ≥ 0 AND Sharpe lift ≥ -0.1 (small tolerance —
we accept marginal Sharpe trade for clear CAGR wins, but not the reverse).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PromotionDecision:
    promote: bool
    cagr_lift: float
    sharpe_lift: float
    reasons: list[str]


def evaluate_promotion(
    mla_metrics: Any,
    rba_metrics: Any,
    *,
    min_cagr_lift: float = 0.0,
    min_sharpe_lift: float = -0.1,
) -> PromotionDecision:
    """Compare two ``BacktestMetrics``-shaped objects (have .cagr & .sharpe)."""
    cagr_lift = float(mla_metrics.cagr) - float(rba_metrics.cagr)
    sharpe_lift = float(mla_metrics.sharpe) - float(rba_metrics.sharpe)

    reasons: list[str] = []
    cagr_ok = cagr_lift >= min_cagr_lift
    sharpe_ok = sharpe_lift >= min_sharpe_lift
    reasons.append(
        f"CAGR lift {cagr_lift:+.2%} {'>=' if cagr_ok else '<'} "
        f"threshold {min_cagr_lift:+.2%} → {'PASS' if cagr_ok else 'FAIL'}"
    )
    reasons.append(
        f"Sharpe lift {sharpe_lift:+.2f} {'>=' if sharpe_ok else '<'} "
        f"threshold {min_sharpe_lift:+.2f} → {'PASS' if sharpe_ok else 'FAIL'}"
    )

    promote = cagr_ok and sharpe_ok
    reasons.append(f"Decision: {'PROMOTE' if promote else 'BLOCK'}")
    return PromotionDecision(
        promote=promote, cagr_lift=cagr_lift, sharpe_lift=sharpe_lift, reasons=reasons,
    )
