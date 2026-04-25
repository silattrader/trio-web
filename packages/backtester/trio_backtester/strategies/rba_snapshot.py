"""RBA-snapshot strategy — uses *today's* RBA scores against historical prices.

⚠️  LOOKAHEAD BIAS ⚠️
The fundamentals (Altman-Z, dividend yield, analyst sentiment, target return)
are pulled at backtest-runtime, not as-of each historical rebalance date.
A company that went bankrupt in 2018 doesn't appear in today's snapshot at
all; a stock that became a darling in 2024 still scored "BUY" in our 2015
backtest. Results are NOT research-grade.

This exists to demo the engine end-to-end — RBA → portfolio → equity curve
in one click. Path 3 (point-in-time fundamentals) is the right answer for
publishable numbers.

Mechanics: pick the top-N tickers by today's BOS/MOS/4F score; equal-weight
buy-and-hold with monthly (configurable) rebalance to keep weights flat.
"""
from __future__ import annotations

from datetime import date
from typing import Any


def select_top_n(
    score_response: Any,
    top_n: int,
    available: set[str],
) -> list[str]:
    """Pick top-N by final_score, ranked descending. Skips unscored rows."""
    scored = [
        r for r in score_response.results
        if r.final_score is not None and r.ticker in available
    ]
    scored.sort(key=lambda r: r.final_score, reverse=True)
    return [r.ticker for r in scored[:top_n]]


def simulate(
    dates: list[date],
    history: dict[str, dict[date, float]],
    selected: list[str],
    rebalance_days: int,
    initial_capital: float,
    fee_bps: float,
) -> tuple[list[float], list[float]]:
    """Equal-weight buy-and-hold across `selected`; rebalance every N days."""
    if not selected or not dates:
        return [initial_capital] * max(len(dates), 1), []

    aligned: dict[str, list[float | None]] = {}
    for t in selected:
        dmap = history.get(t, {})
        last: float | None = None
        series: list[float | None] = []
        for d in dates:
            v = dmap.get(d, last)
            last = v if v is not None else last
            series.append(last)
        aligned[t] = series

    fee = fee_bps / 10_000.0
    n = len(selected)
    target = 1.0 / n
    weights = {t: target for t in selected}

    equity = [initial_capital]
    # Charge entry fee day 0.
    equity[0] *= 1 - fee

    bars_since_rebal = 0
    trade_returns: list[float] = []
    cum_per_ticker: dict[str, float] = {t: 0.0 for t in selected}

    for i in range(1, len(dates)):
        port_return = 0.0
        for t, w in weights.items():
            p_prev = aligned[t][i - 1]
            p_now = aligned[t][i]
            if p_prev and p_now:
                r = p_now / p_prev - 1
                port_return += w * r
                cum_per_ticker[t] = (1 + cum_per_ticker[t]) * (1 + r) - 1
        equity.append(equity[-1] * (1 + port_return))

        bars_since_rebal += 1
        if bars_since_rebal >= rebalance_days:
            # Rebalance back to equal weights — small turnover unless drift is huge.
            # For a flat reset, turnover ≈ 2 * sum(|w_drift - target|).
            # Approximate weights post-drift from cum returns.
            drift = {t: target * (1 + cum_per_ticker[t]) for t in selected}
            tot = sum(drift.values()) or 1.0
            drift = {t: drift[t] / tot for t in selected}
            turnover = sum(abs(drift[t] - target) for t in selected)
            equity[-1] *= 1 - turnover * fee
            cum_per_ticker = {t: 0.0 for t in selected}
            weights = {t: target for t in selected}
            bars_since_rebal = 0

    # Each ticker's full-period return is one "trade" for win-rate purposes.
    for t in selected:
        if aligned[t][0] and aligned[t][-1]:
            trade_returns.append(aligned[t][-1] / aligned[t][0] - 1)

    return equity, trade_returns
