"""Promotion-gate runner — the policy function that decides whether MLA
is allowed to ship as the default model.

Runs two ``rba_pit`` backtests over the same out-of-sample period:
1. model="bos"     — RBA baseline
2. model="mla_v0"  — gradient-boosted, loaded from a specified artifact

Then calls ``evaluate_promotion`` on the two backtest metrics.

Honesty caveat: the trained MLA artifact may overlap with the test period
if you didn't enforce a strict train/test split during training. The gate
catches "MLA not better than RBA"; it does NOT catch leakage. For real
promotion, train on 2018-2021 only, test on 2022-2023.

CLI: ``python -m trio_algorithms.mla.promote --start 2022-01-03 --end 2023-12-29 \\
              --artifact path/to/mla_v1.joblib``
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .data_pipeline import DEFAULT_UNIVERSE
from .gate import PromotionDecision, evaluate_promotion


def _parse_iso(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def run_gate(
    *,
    start: date,
    end: date,
    artifact: Path,
    universe: list[str] | None = None,
    top_n: int = 5,
    rebalance_days: int = 63,
    fee_bps: float = 5.0,
) -> tuple[Any, Any, PromotionDecision]:
    """Run RBA-BOS vs MLA-v0 backtests + apply the gate.

    Returns ``(rba_response, mla_response, decision)``. Both responses are
    full ``BacktestResponse`` objects so callers can render full equity
    curves alongside the headline gate decision.
    """
    from trio_backtester import BacktestRequest, run_backtest
    from trio_backtester.data import fetch_history, fetch_volume_history
    from trio_data_providers import EdgarPitProvider

    from ..rba.bos import score_bos
    from .inference import score_mla_v0

    universe = universe or DEFAULT_UNIVERSE
    _, prices = fetch_history(universe, start, end)
    if not prices:
        raise RuntimeError("yfinance returned no price history for the universe.")
    volumes = fetch_volume_history(universe, start, end)
    pit = EdgarPitProvider()

    def _score_fn(model_name: str):
        def _fn(tickers, model, as_of):
            res = pit.fetch_as_of(
                tickers, as_of=as_of, model=model_name,
                prices=prices, volumes=volumes,
            )
            u = f"PIT@{as_of.isoformat()}"
            if model_name == "mla_v0":
                return score_mla_v0(res.rows, universe=u, artifact=artifact)
            return score_bos(res.rows, universe=u)
        return _fn

    dates = sorted({d for series in prices.values() for d in series})

    req = BacktestRequest(
        tickers=universe, start=start, end=end,
        top_n=top_n, rebalance_days=rebalance_days, fee_bps=fee_bps,
    )

    rba = run_backtest(
        req, "rba_pit", history=prices, dates=dates,
        score_fn=_score_fn("bos"),
    )
    mla = run_backtest(
        req, "rba_pit", history=prices, dates=dates,
        score_fn=_score_fn("mla_v0"),
    )

    decision = evaluate_promotion(mla.metrics, rba.metrics)
    return rba, mla, decision


def main() -> None:  # pragma: no cover (CLI)
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=_parse_iso, required=True)
    p.add_argument("--end", type=_parse_iso, required=True)
    p.add_argument("--artifact", type=Path, required=True)
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--rebalance-days", type=int, default=63)
    args = p.parse_args()

    rba, mla, decision = run_gate(
        start=args.start, end=args.end, artifact=args.artifact,
        top_n=args.top_n, rebalance_days=args.rebalance_days,
    )

    print("=" * 60)
    print(f"Period: {args.start} -> {args.end}")
    print(f"{'':>8s}  {'CAGR':>7s}  {'Sharpe':>7s}  {'MaxDD':>7s}  {'TotRet':>7s}")
    print(f"{'RBA-BOS':>8s}  {rba.metrics.cagr:>7.2%}  {rba.metrics.sharpe:>7.2f}  "
          f"{rba.metrics.max_drawdown:>7.2%}  {rba.metrics.total_return:>7.2%}")
    print(f"{'MLA v0':>8s}  {mla.metrics.cagr:>7.2%}  {mla.metrics.sharpe:>7.2f}  "
          f"{mla.metrics.max_drawdown:>7.2%}  {mla.metrics.total_return:>7.2%}")
    print("-" * 60)
    for r in decision.reasons:
        print(f"  {r}")
    print("=" * 60)
    print(f"GATE: {'PROMOTE' if decision.promote else 'BLOCK'}")


if __name__ == "__main__":  # pragma: no cover
    main()
