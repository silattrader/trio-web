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
    score_mla_v0,
    score_mos,
)
from trio_backtester import (
    BacktestRequest,
    BacktestResponse,
    WalkForwardResponse,
    run_backtest,
    run_walk_forward,
)
from trio_backtester.data import fetch_history, fetch_volume_history
from trio_data_providers import (
    EdgarPitProvider,
    MockPitProvider,
    PitProvider,
    ProviderError,
    get_provider,
    list_providers,
)

ModelName = Literal["bos", "mos", "four_factor", "mla_v0"]

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
        "mla": [
            {"id": "mla_v0", "version": "mla-v0.1.0", "label": "Gradient-Boosted (preview)"},
        ],
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
    if model == "mla_v0":
        return score_mla_v0(req.rows, universe=req.universe)

    raise HTTPException(status_code=400, detail=f"unknown model: {model}")


class UniverseRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=1, max_length=200)


@app.get("/providers")
def providers() -> dict:
    return {"providers": list_providers()}


StrategyName = Literal["sma", "rba_snapshot", "rba_pit"]


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
    if model == "mla_v0":
        return score_mla_v0(res.rows, universe=res.universe)
    return score_four_factor(res.rows, universe=res.universe)


def _make_pit_provider() -> PitProvider:
    """Pick the PIT provider at startup.

    Set ``TRIO_PIT_PROVIDER=edgar`` to use the real SEC EDGAR adapter (US
    tickers only; requires ``TRIO_SEC_UA`` env to a contact email per SEC
    rules). Default is the deterministic-synthetic MockPitProvider.
    """
    import os
    choice = os.environ.get("TRIO_PIT_PROVIDER", "mock").lower()
    if choice == "edgar":
        return EdgarPitProvider()
    return MockPitProvider()


_pit_provider: PitProvider = _make_pit_provider()


def _make_pit_score_fn(
    history: dict | None = None, volumes: dict | None = None
):
    """Build a PIT-aware score_fn that closes over pre-fetched prices+volumes.

    EdgarPitProvider uses these to compute market dividend yield (DPS / as-of
    price) and vol_avg_3m (63-day rolling). MockPitProvider ignores them.
    """
    def _fn(tickers: list[str], model: str, as_of) -> ScoreResponse:
        pit = _pit_provider.fetch_as_of(
            tickers, as_of=as_of, model=model,
            prices=history, volumes=volumes,
        )
        u = f"PIT@{as_of.isoformat()}"
        if model == "bos":
            return score_bos(pit.rows, universe=u)
        if model == "mos":
            return score_mos(pit.rows, universe=u)
        if model == "mla_v0":
            return score_mla_v0(pit.rows, universe=u)
        return score_four_factor(pit.rows, universe=u)
    return _fn


# Back-compat module-level function — no prices/volumes (used by tests that
# don't go through the /backtest endpoint).
_pit_score_for_backtest = _make_pit_score_fn()


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

    if strategy == "rba_pit":
        # Fetch volumes once so EdgarPitProvider can compute vol_avg_3m
        # point-in-time. Mock ignores it. Cached on yfinance side.
        try:
            volumes = fetch_volume_history(req.tickers, req.start, req.end)
        except Exception:  # noqa: BLE001
            volumes = {}
        score_fn = _make_pit_score_fn(history=history, volumes=volumes)
    elif strategy == "rba_snapshot":
        score_fn = _score_for_backtest
    else:
        score_fn = None
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

    if strategy == "rba_pit":
        try:
            volumes = fetch_volume_history(req.tickers, req.start, req.end)
        except Exception:  # noqa: BLE001
            volumes = {}
        score_fn = _make_pit_score_fn(history=history, volumes=volumes)
    elif strategy == "rba_snapshot":
        score_fn = _score_for_backtest
    else:
        score_fn = None
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
