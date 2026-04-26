"""TRIO Web API — P1 RBA scoring service.

POST /score?model={bos|mos|four_factor}  -> ScoreResponse
"""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from trio_algorithms import (
    ScoreRequest,
    ScoreResponse,
    score_bos,
    score_four_factor,
    score_mos,
)
from trio_backtester import (
    BacktestRequest,
    BacktestResponse,
    WalkForwardResponse,
    run_backtest,
    run_walk_forward,
)
from trio_backtester.data import fetch_history
from trio_data_providers import ProviderError, get_provider, list_providers

ModelName = Literal["bos", "mos", "four_factor"]

app = FastAPI(
    title="TRIO Web API",
    version="0.1.0",
    description="Rule-based equity scoring (RBA). MLA endpoints land in P5+.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/models")
def list_models() -> dict:
    return {
        "rba": [
            {"id": "bos", "version": "rba-bos-1.0.0", "label": "5-Factor Buy-or-Sell"},
            {"id": "mos", "version": "rba-mos-1.0.0", "label": "Margin-of-Safety (Graham)"},
            {"id": "four_factor", "version": "rba-four-factor-1.0.0", "label": "4-Factor Legacy"},
        ],
        "mla": [],
    }


@app.post("/score", response_model=ScoreResponse)
def score(
    req: ScoreRequest,
    model: ModelName = Query("bos"),
    legacy: bool = Query(False, description="four_factor only — preserve original main.py bug"),
) -> ScoreResponse:
    if not req.rows:
        raise HTTPException(status_code=400, detail="rows is empty")

    if model == "bos":
        return score_bos(req.rows, universe=req.universe, weights=req.bos_weights)
    if model == "mos":
        return score_mos(req.rows, universe=req.universe)
    if model == "four_factor":
        return score_four_factor(req.rows, universe=req.universe, legacy=legacy)

    raise HTTPException(status_code=400, detail=f"unknown model: {model}")


class UniverseRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=1, max_length=200)


@app.get("/providers")
def providers() -> dict:
    return {"providers": list_providers()}


StrategyName = Literal["sma", "rba_snapshot"]


def _score_for_backtest(tickers: list[str], model: str, _as_of) -> ScoreResponse:
    """Pull live yfinance rows and run RBA scoring — used by rba_snapshot.

    NOTE: deliberately uses *current* fundamentals, not point-in-time. This is
    the source of the lookahead warning surfaced by the engine.
    """
    provider = get_provider("yfinance")
    res = provider.fetch(tickers, model=model)
    if model == "bos":
        return score_bos(res.rows, universe=res.universe)
    if model == "mos":
        return score_mos(res.rows, universe=res.universe)
    return score_four_factor(res.rows, universe=res.universe)


@app.post("/backtest", response_model=BacktestResponse)
def backtest(
    req: BacktestRequest,
    strategy: StrategyName = Query("sma"),
) -> BacktestResponse:
    """Run a hosted backtest. SMA = price-only (no lookahead). rba_snapshot =
    today's RBA scores against history (lookahead-flagged in warnings)."""
    if req.end <= req.start:
        raise HTTPException(status_code=400, detail="end must be after start")

    try:
        dates, history = fetch_history(req.tickers, req.start, req.end)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"price-history fetch failed: {e}") from e

    if not dates:
        raise HTTPException(status_code=502, detail="no price history returned for these tickers/dates")

    score_fn = _score_for_backtest if strategy == "rba_snapshot" else None
    return run_backtest(req, strategy, history=history, dates=dates, score_fn=score_fn)


@app.post("/backtest/walk_forward", response_model=WalkForwardResponse)
def backtest_walk_forward(
    req: BacktestRequest,
    strategy: StrategyName = Query("sma"),
    n_windows: int = Query(4, ge=2, le=12),
) -> WalkForwardResponse:
    """Split [start, end] into N non-overlapping windows; run the strategy on
    each. Surfaces consistency, not a single lucky equity curve."""
    if req.end <= req.start:
        raise HTTPException(status_code=400, detail="end must be after start")

    try:
        dates, history = fetch_history(req.tickers, req.start, req.end)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"price-history fetch failed: {e}") from e

    if not dates:
        raise HTTPException(status_code=502, detail="no price history returned for these tickers/dates")

    score_fn = _score_for_backtest if strategy == "rba_snapshot" else None
    return run_walk_forward(
        req, strategy,
        n_windows=n_windows,
        history=history, dates=dates, score_fn=score_fn,
    )


@app.post("/universe/{provider_name}")
def fetch_universe(
    provider_name: str,
    req: UniverseRequest,
    model: ModelName = Query("bos"),
) -> dict:
    """Fetch live rows from a data provider, mapped to canonical scoring fields.

    Returns provider rows + warnings; the client then POSTs them to /score.
    Keeps /score universe-blind (single contract for RBA + future MLA).
    """
    try:
        provider = get_provider(provider_name)
        result = provider.fetch(req.tickers, model=model)
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return {
        "provider": result.provider,
        "universe": result.universe,
        "rows": result.rows,
        "warnings": result.warnings,
        "coverage": sorted(provider.coverage(model)),
    }
