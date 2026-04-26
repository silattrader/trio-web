"""TRIO backtester — hosted equity-curve simulator.

Two strategies live here:

* ``sma`` — price-only SMA crossover. No fundamentals → no lookahead.
* ``rba_snapshot`` — uses *today's* RBA scores against historical prices.
  Honest about the lookahead bias via a mandatory warning. Useful for
  demoing the engine end-to-end; **not** a research-grade backtest.

Walk-forward (``run_walk_forward``) re-runs either strategy on N non-overlapping
sub-windows and aggregates the dispersion. Cheap consistency check before
committing to any one equity curve.

Path 3 (point-in-time fundamentals) is deferred to P5+.
"""
from .contracts import (
    BacktestRequest,
    BacktestResponse,
    EquityPoint,
    Metrics,
    WalkForwardAggregate,
    WalkForwardResponse,
    WalkForwardWindow,
)
from .engine import run_backtest
from .walk_forward import run_walk_forward

__all__ = [
    "BacktestRequest",
    "BacktestResponse",
    "EquityPoint",
    "Metrics",
    "WalkForwardAggregate",
    "WalkForwardResponse",
    "WalkForwardWindow",
    "run_backtest",
    "run_walk_forward",
]
