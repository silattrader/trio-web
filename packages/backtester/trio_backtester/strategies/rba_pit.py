"""rba_pit — point-in-time RBA strategy (Path 3).

Differs from `rba_snapshot` in one important way: the universe is re-scored
*at every rebalance date*, using fundamentals as-of that date. No lookahead
when paired with a real PIT provider.

Mechanics:
1. At t=0 and every `rebalance_days` bars, call ``pit_score_fn(tickers, model, as_of)``.
2. Pick top-N by `final_score`.
3. Rebalance the portfolio to equal-weight the (possibly new) selection.
4. Charge fees on turnover (sum of |Δw| × fee_rate).

The selection drifts over time, which is the whole point — that's how an
honest backtest reflects regime changes.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

PitScoreFn = Callable[[list[str], str, date], Any]


def _aligned_prices(
    dates: list[date], tickers: list[str], history: dict[str, dict[date, float]]
) -> dict[str, list[float | None]]:
    """Per-ticker forward-filled price series indexed by `dates`."""
    out: dict[str, list[float | None]] = {}
    for t in tickers:
        dmap = history.get(t, {})
        last: float | None = None
        series: list[float | None] = []
        for d in dates:
            v = dmap.get(d, last)
            last = v if v is not None else last
            series.append(last)
        out[t] = series
    return out


def select_top_n_from_resp(score_response: Any, top_n: int, available: set[str]) -> list[str]:
    scored = [
        r for r in score_response.results
        if r.final_score is not None and r.ticker in available
    ]
    scored.sort(key=lambda r: r.final_score, reverse=True)
    return [r.ticker for r in scored[:top_n]]


def simulate(
    *,
    dates: list[date],
    history: dict[str, dict[date, float]],
    tickers: list[str],
    model: str,
    top_n: int,
    rebalance_days: int,
    initial_capital: float,
    fee_bps: float,
    pit_score_fn: PitScoreFn,
) -> tuple[list[float], list[float], list[tuple[date, list[str]]]]:
    """Returns (equity_curve, trade_returns, rebalance_log).

    `rebalance_log` is a list of `(as_of_date, selected_tickers)` for every
    rebalance — surface this so the UI can show how the portfolio evolved.
    """
    if not dates:
        return [initial_capital], [], []

    universe_prices = _aligned_prices(dates, tickers, history)
    available_at = lambda i: {  # noqa: E731
        t for t in tickers if universe_prices[t][i] is not None
    }

    fee = fee_bps / 10_000.0
    equity = [initial_capital]
    weights: dict[str, float] = {}
    rebalance_log: list[tuple[date, list[str]]] = []
    trade_entry_prices: dict[str, float] = {}
    trade_returns: list[float] = []

    def rebalance_to(i: int, selected: list[str]) -> None:
        nonlocal weights
        target = 1.0 / len(selected) if selected else 0.0
        new_weights = {t: target for t in selected}
        # Turnover = sum of |Δw| across union of old + new tickers.
        union = set(weights) | set(new_weights)
        turnover = sum(abs(new_weights.get(t, 0.0) - weights.get(t, 0.0)) for t in union)
        equity[-1] *= 1 - turnover * fee
        # Close trades for tickers being dropped or down-weighted.
        for t in weights:
            if t not in new_weights:
                p_now = universe_prices[t][i]
                p_in = trade_entry_prices.get(t)
                if p_now and p_in:
                    trade_returns.append(p_now / p_in - 1)
                trade_entry_prices.pop(t, None)
        # Open trades for new tickers.
        for t in new_weights:
            if t not in weights:
                p_now = universe_prices[t][i]
                if p_now:
                    trade_entry_prices[t] = p_now
        weights = new_weights
        rebalance_log.append((dates[i], list(new_weights)))

    # Initial selection at t=0.
    score0 = pit_score_fn(tickers, model, dates[0])
    sel0 = select_top_n_from_resp(score0, top_n, available_at(0))
    rebalance_to(0, sel0)

    bars_since = 0
    for i in range(1, len(dates)):
        port_return = 0.0
        for t, w in weights.items():
            p_prev = universe_prices[t][i - 1]
            p_now = universe_prices[t][i]
            if p_prev and p_now:
                port_return += w * (p_now / p_prev - 1)
        equity.append(equity[-1] * (1 + port_return))

        bars_since += 1
        if bars_since >= rebalance_days and i < len(dates) - 1:
            score_i = pit_score_fn(tickers, model, dates[i])
            sel_i = select_top_n_from_resp(score_i, top_n, available_at(i))
            if sel_i:
                rebalance_to(i, sel_i)
            bars_since = 0

    # Close any remaining open trades at end-of-period.
    for t, p_in in trade_entry_prices.items():
        p_end = universe_prices[t][-1]
        if p_end and p_in:
            trade_returns.append(p_end / p_in - 1)

    return equity, trade_returns, rebalance_log
