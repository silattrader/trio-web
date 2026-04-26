"""Walk-forward backtest — split the date range into N non-overlapping windows
and run the chosen strategy on each, then summarise the dispersion.

This is the cheapest credibility check available: a single equity curve from
2018→2024 might be one lucky regime; four sub-windows tell you whether the
strategy is consistent or just happened to ride one bull leg.

Pure-function: re-uses ``run_backtest`` per slice. No new data fetches.
"""
from __future__ import annotations

import math
from datetime import date

from .contracts import (
    BacktestRequest,
    StrategyId,
    WalkForwardAggregate,
    WalkForwardResponse,
    WalkForwardWindow,
)
from .engine import ScoreFn, run_backtest


def _split_indices(n: int, k: int) -> list[tuple[int, int]]:
    """Split [0, n) into k contiguous, near-equal slices. Returns [(lo, hi), ...]
    where hi is exclusive. Drops empty slices if n < k."""
    if k <= 0:
        raise ValueError("n_windows must be >= 1")
    k = min(k, n)
    if k == 0:
        return []
    base = n // k
    extra = n % k  # first `extra` slices get one more day
    out: list[tuple[int, int]] = []
    cur = 0
    for i in range(k):
        size = base + (1 if i < extra else 0)
        out.append((cur, cur + size))
        cur += size
    return [(lo, hi) for lo, hi in out if hi - lo >= 2]  # need >=2 days for returns


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mu = sum(xs) / len(xs)
    var = sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def run_walk_forward(
    req: BacktestRequest,
    strategy: StrategyId,
    *,
    n_windows: int,
    history: dict[str, dict[date, float]],
    dates: list[date],
    score_fn: ScoreFn | None = None,
) -> WalkForwardResponse:
    """Slice ``dates`` into ``n_windows`` chunks; run the strategy on each."""
    if n_windows < 2:
        raise ValueError("walk-forward needs n_windows >= 2 (else use /backtest)")

    slices = _split_indices(len(dates), n_windows)
    warnings: list[str] = []
    if len(slices) < n_windows:
        warnings.append(
            f"Requested {n_windows} windows but only {len(slices)} have >=2 days "
            "of price data; remaining windows dropped."
        )

    windows: list[WalkForwardWindow] = []
    for i, (lo, hi) in enumerate(slices):
        win_dates = dates[lo:hi]
        # Slice each ticker's price map to the window — keeps run_backtest pure.
        win_hist = {
            t: {d: p for d, p in series.items() if win_dates[0] <= d <= win_dates[-1]}
            for t, series in history.items()
        }
        win_req = req.model_copy(update={"start": win_dates[0], "end": win_dates[-1]})
        sub = run_backtest(
            win_req, strategy,
            history=win_hist, dates=win_dates, score_fn=score_fn,
        )
        bench_total = sub.benchmark_metrics.total_return if sub.benchmark_metrics else 0.0
        windows.append(
            WalkForwardWindow(
                index=i,
                start=win_dates[0],
                end=win_dates[-1],
                metrics=sub.metrics,
                benchmark_metrics=sub.benchmark_metrics,
                beat_benchmark=sub.metrics.total_return > bench_total,
            )
        )
        # Bubble per-window warnings (e.g. lookahead) but only once.
        for w in sub.warnings:
            if w not in warnings:
                warnings.append(w)

    if not windows:
        # Fall back to an empty aggregate rather than 500'ing.
        agg = WalkForwardAggregate(
            n_windows=0, mean_sharpe=0.0, median_total_return=0.0,
            total_return_std=0.0, pct_windows_beating_benchmark=0.0,
            pct_windows_positive=0.0,
        )
    else:
        sharpes = [w.metrics.sharpe for w in windows]
        totals = [w.metrics.total_return for w in windows]
        agg = WalkForwardAggregate(
            n_windows=len(windows),
            mean_sharpe=sum(sharpes) / len(sharpes),
            median_total_return=_median(totals),
            total_return_std=_stdev(totals),
            pct_windows_beating_benchmark=(
                sum(1 for w in windows if w.beat_benchmark) / len(windows)
            ),
            pct_windows_positive=(
                sum(1 for t in totals if t > 0) / len(windows)
            ),
        )

    return WalkForwardResponse(
        strategy=strategy,
        universe_size=len(req.tickers),
        start=dates[0] if dates else req.start,
        end=dates[-1] if dates else req.end,
        windows=windows,
        aggregate=agg,
        warnings=warnings,
    )
