"""Engine orchestrator. Routes (request, history) → BacktestResponse."""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from .contracts import (
    BacktestRequest,
    BacktestResponse,
    EquityPoint,
    Metrics,
    StrategyId,
)
from .metrics import summarise
from .strategies import rba_snapshot, sma

LOOKAHEAD_WARNING = (
    "rba_snapshot uses TODAY's RBA scores against historical prices — "
    "results suffer from lookahead and survivorship bias. Demo only; "
    "Path 3 (point-in-time fundamentals) is needed for publishable numbers."
)

ScoreFn = Callable[[list[str], str, date], Any]
"""(tickers, model, as_of) -> ScoreResponse-like object with .results[].final_score & .ticker"""


def _benchmark_curve(
    dates: list[date],
    history: dict[str, dict[date, float]],
    tickers: list[str],
    initial_capital: float,
) -> list[float]:
    """Equal-weight buy-and-hold across the input universe — the 'do-nothing' baseline."""
    if not dates or not tickers:
        return [initial_capital] * max(len(dates), 1)

    available = [t for t in tickers if t in history and history[t]]
    if not available:
        return [initial_capital] * len(dates)

    n = len(available)
    base_prices: dict[str, float] = {}
    for t in available:
        # First non-None price.
        for d in dates:
            v = history[t].get(d)
            if v is not None:
                base_prices[t] = v
                break

    curve = []
    for d in dates:
        port = 0.0
        for t in available:
            base = base_prices.get(t)
            if not base:
                continue
            p = history[t].get(d)
            if p is None:
                # Forward-fill from prior date.
                idx = dates.index(d)
                while idx > 0 and p is None:
                    idx -= 1
                    p = history[t].get(dates[idx])
            if p is not None:
                port += (1 / n) * (p / base)
        curve.append(initial_capital * port)
    return curve


def run_backtest(
    req: BacktestRequest,
    strategy: StrategyId,
    *,
    history: dict[str, dict[date, float]],
    dates: list[date],
    score_fn: ScoreFn | None = None,
) -> BacktestResponse:
    """Pure-function entry point. Caller owns price-history + scoring fetches.

    `history` and `dates` are passed in so the FastAPI layer (or tests) can
    decide how to source prices — yfinance, fixtures, or anything else.
    """
    warnings: list[str] = []
    universe_size = len(req.tickers)

    if strategy == "sma":
        equity, trade_rets = sma.simulate(
            dates=dates,
            history=history,
            fast=req.fast,
            slow=req.slow,
            initial_capital=req.initial_capital,
            fee_bps=req.fee_bps,
        )

    elif strategy == "rba_snapshot":
        warnings.append(LOOKAHEAD_WARNING)
        if score_fn is None:
            raise ValueError("rba_snapshot requires score_fn")
        score_resp = score_fn(req.tickers, req.model, req.start)
        selected = rba_snapshot.select_top_n(
            score_resp, req.top_n, available=set(history.keys())
        )
        if not selected:
            warnings.append("RBA produced no scored tickers — backtest aborted.")
            equity, trade_rets = [req.initial_capital] * max(len(dates), 1), []
        else:
            warnings.append(
                f"Selected top {len(selected)} by {req.model.upper()} score: "
                + ", ".join(selected)
            )
            equity, trade_rets = rba_snapshot.simulate(
                dates=dates,
                history=history,
                selected=selected,
                rebalance_days=req.rebalance_days,
                initial_capital=req.initial_capital,
                fee_bps=req.fee_bps,
            )

    else:  # pragma: no cover
        raise ValueError(f"unknown strategy: {strategy}")

    bench = _benchmark_curve(dates, history, req.tickers, req.initial_capital)

    n_days = max(len(dates) - 1, 1)
    strat_summary = summarise(equity, n_days, trade_rets)
    bench_summary = summarise(bench, n_days, None)

    points = [
        EquityPoint(
            date=dates[i],
            value=round(equity[i], 2) if i < len(equity) else equity[-1],
            benchmark=round(bench[i], 2) if i < len(bench) else None,
        )
        for i in range(len(dates))
    ]

    return BacktestResponse(
        strategy=strategy,
        universe_size=universe_size,
        start=req.start,
        end=req.end,
        equity_curve=points,
        metrics=Metrics(**strat_summary),
        benchmark_metrics=Metrics(**bench_summary),
        warnings=warnings,
    )
