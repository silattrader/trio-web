"""Pydantic contracts for /backtest. Mirror in apps/web/lib/api.ts."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

StrategyId = Literal["sma", "rba_snapshot"]
ModelId = Literal["bos", "mos", "four_factor"]


class BacktestRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=1, max_length=50)
    start: date
    end: date
    initial_capital: float = Field(default=100_000.0, gt=0)

    # SMA-specific
    fast: int = Field(default=50, ge=2, le=400)
    slow: int = Field(default=200, ge=5, le=600)

    # rba_snapshot-specific
    model: ModelId = "bos"
    top_n: int = Field(default=3, ge=1, le=20)
    rebalance_days: int = Field(default=21, ge=1, le=252)

    # cost model
    fee_bps: float = Field(default=5.0, ge=0, le=200, description="round-trip bps")


class EquityPoint(BaseModel):
    date: date
    value: float
    benchmark: float | None = None


class Metrics(BaseModel):
    cagr: float
    sharpe: float
    max_drawdown: float
    total_return: float
    n_trades: int
    win_rate: float | None = None


class BacktestResponse(BaseModel):
    strategy: StrategyId
    universe_size: int
    start: date
    end: date
    equity_curve: list[EquityPoint]
    metrics: Metrics
    benchmark_metrics: Metrics | None = None
    warnings: list[str]


# --- Walk-forward ---------------------------------------------------------


class WalkForwardWindow(BaseModel):
    """Per-window slice metrics. Beat-benchmark = strategy total return > benchmark."""

    index: int
    start: date
    end: date
    metrics: Metrics
    benchmark_metrics: Metrics | None = None
    beat_benchmark: bool


class WalkForwardAggregate(BaseModel):
    """Cross-window summary — the actual signal that the engine isn't lucky."""

    n_windows: int
    mean_sharpe: float
    median_total_return: float
    total_return_std: float
    pct_windows_beating_benchmark: float
    pct_windows_positive: float


class WalkForwardResponse(BaseModel):
    strategy: StrategyId
    universe_size: int
    start: date
    end: date
    windows: list[WalkForwardWindow]
    aggregate: WalkForwardAggregate
    warnings: list[str]
