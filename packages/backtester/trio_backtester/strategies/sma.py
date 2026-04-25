"""SMA crossover strategy — pure price, no fundamentals → no lookahead.

Per ticker, hold long when fast-SMA > slow-SMA, flat otherwise. Equal-weight
across the active long names; rebalance daily as signals flip. Round-trip
fees deducted on each weight change per ticker.
"""
from __future__ import annotations

from datetime import date


def _sma(values: list[float], window: int, end_idx: int) -> float | None:
    if end_idx + 1 < window:
        return None
    s = 0.0
    for i in range(end_idx + 1 - window, end_idx + 1):
        s += values[i]
    return s / window


def signal_series(
    closes: list[float], fast: int, slow: int
) -> list[bool]:
    """True at index i means 'go long after close on day i' (entered next bar).

    Caller is responsible for shifting one bar forward when applying the
    signal to returns; signal_series itself is computed using only data
    available up to and including day i, so no lookahead inside this fn.
    """
    out: list[bool] = []
    for i in range(len(closes)):
        f = _sma(closes, fast, i)
        s = _sma(closes, slow, i)
        out.append(f is not None and s is not None and f > s)
    return out


def simulate(
    dates: list[date],
    history: dict[str, dict[date, float]],
    fast: int,
    slow: int,
    initial_capital: float,
    fee_bps: float,
) -> tuple[list[float], list[float]]:
    """Returns (equity_curve, trade_returns_per_segment).

    Equal-weight across tickers currently long. Daily mark-to-market.
    A 'trade' = one continuous long episode in one ticker.
    """
    if not dates:
        return [], []

    # Forward-fill prices into a per-ticker aligned series.
    aligned: dict[str, list[float | None]] = {}
    for t, dmap in history.items():
        last: float | None = None
        series: list[float | None] = []
        for d in dates:
            v = dmap.get(d, last)
            last = v if v is not None else last
            series.append(last)
        aligned[t] = series

    # Per-ticker signals (computed only from past closes → no lookahead).
    signals: dict[str, list[bool]] = {}
    for t, series in aligned.items():
        closes = [v if v is not None else 0.0 for v in series]
        signals[t] = signal_series(closes, fast, slow)

    fee = fee_bps / 10_000.0
    equity = [initial_capital]
    prev_weights: dict[str, float] = {t: 0.0 for t in aligned}
    trade_pnl: dict[str, float] = {t: 0.0 for t in aligned}
    open_trade: dict[str, bool] = {t: False for t in aligned}
    trade_returns: list[float] = []

    for i in range(1, len(dates)):
        # Signal on day i-1 governs exposure during day i (no lookahead).
        active = [t for t in aligned if signals[t][i - 1] and aligned[t][i - 1]]
        n = len(active)
        target_weights = {t: (1.0 / n if t in active else 0.0) for t in aligned}

        # Per-ticker daily return.
        port_return = 0.0
        for t, w in target_weights.items():
            p_prev = aligned[t][i - 1]
            p_now = aligned[t][i]
            if w > 0 and p_prev and p_now:
                r = p_now / p_prev - 1
                port_return += w * r
                if not open_trade[t]:
                    open_trade[t] = True
                    trade_pnl[t] = 0.0
                trade_pnl[t] = (1 + trade_pnl[t]) * (1 + r) - 1
            elif open_trade[t] and w == 0:
                trade_returns.append(trade_pnl[t])
                open_trade[t] = False
                trade_pnl[t] = 0.0

        # Round-trip fees on weight changes.
        turnover = sum(abs(target_weights[t] - prev_weights[t]) for t in aligned)
        port_return -= turnover * fee
        prev_weights = target_weights

        equity.append(equity[-1] * (1 + port_return))

    # Close any still-open trades at the end.
    for t, open_ in open_trade.items():
        if open_:
            trade_returns.append(trade_pnl[t])

    return equity, trade_returns
