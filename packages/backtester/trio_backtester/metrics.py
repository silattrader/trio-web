"""Equity-curve summary metrics. Pure functions; no I/O."""
from __future__ import annotations

import math

TRADING_DAYS = 252


def daily_returns(values: list[float]) -> list[float]:
    """Simple returns r_t = v_t / v_{t-1} - 1, length n-1."""
    out: list[float] = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        if prev <= 0:
            out.append(0.0)
        else:
            out.append(values[i] / prev - 1.0)
    return out


def cagr(values: list[float], n_days: int) -> float:
    if not values or values[0] <= 0 or n_days <= 0:
        return 0.0
    years = n_days / TRADING_DAYS
    if years <= 0:
        return 0.0
    return (values[-1] / values[0]) ** (1 / years) - 1


def sharpe(returns: list[float], rf_daily: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    excess = [r - rf_daily for r in returns]
    mean = sum(excess) / len(excess)
    var = sum((r - mean) ** 2 for r in excess) / (len(excess) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return (mean / sd) * math.sqrt(TRADING_DAYS)


def max_drawdown(values: list[float]) -> float:
    """Returns the max peak-to-trough decline as a *negative* fraction."""
    peak = -math.inf
    worst = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = v / peak - 1
            if dd < worst:
                worst = dd
    return worst


def total_return(values: list[float]) -> float:
    if len(values) < 2 or values[0] <= 0:
        return 0.0
    return values[-1] / values[0] - 1


def win_rate(trade_returns: list[float]) -> float | None:
    if not trade_returns:
        return None
    wins = sum(1 for r in trade_returns if r > 0)
    return wins / len(trade_returns)


def summarise(
    values: list[float], n_days: int, trade_returns: list[float] | None = None
) -> dict:
    rets = daily_returns(values)
    return {
        "cagr": cagr(values, n_days),
        "sharpe": sharpe(rets),
        "max_drawdown": max_drawdown(values),
        "total_return": total_return(values),
        "n_trades": len(trade_returns) if trade_returns else 0,
        "win_rate": win_rate(trade_returns) if trade_returns else None,
    }
