"""TRIO backtester — hosted equity-curve simulator.

Two strategies live here:

* ``sma`` — price-only SMA crossover. No fundamentals → no lookahead.
* ``rba_snapshot`` — uses *today's* RBA scores against historical prices.
  Honest about the lookahead bias via a mandatory warning. Useful for
  demoing the engine end-to-end; **not** a research-grade backtest.

Path 3 (point-in-time fundamentals) is deferred to P5+.
"""
from .contracts import (
    BacktestRequest,
    BacktestResponse,
    EquityPoint,
    Metrics,
)
from .engine import run_backtest

__all__ = [
    "BacktestRequest",
    "BacktestResponse",
    "EquityPoint",
    "Metrics",
    "run_backtest",
]
