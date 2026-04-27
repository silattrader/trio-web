"""TRIO Web API — P1 RBA scoring service.

POST /score?model={bos|mos|four_factor}  -> ScoreResponse
"""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from trio_algorithms import (
    ScoreRequest,
    ScoreResponse,
    score_bos,
    score_bos_flow,
    score_four_factor,
    score_mla_v0,
    score_mos,
    score_qv,
    simulate_shock,
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
    ALL_UNIVERSES,
    EdgarPitProvider,
    FmpPitProvider,
    InsiderFlowPitProvider,
    MergedPitProvider,
    MockPitProvider,
    PitProvider,
    ProviderError,
    RetailFlowPitProvider,
    get_provider,
    list_providers,
)
from trio_data_providers._request_keys import (
    RequestKeys,
    set_request_keys,
    reset_request_keys,
)

ModelName = Literal["bos", "bos_flow", "qv", "mos", "four_factor", "mla_v0"]

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


@app.middleware("http")
async def byok_middleware(request, call_next):
    """Read user-supplied API keys from request headers and bind them to
    the contextvars that low-level provider clients consult.

    Headers (all optional):
      X-TRIO-SEC-UA   — SEC EDGAR contact email
      X-TRIO-FMP-KEY  — Financial Modeling Prep API key
      X-TRIO-WIKI-UA  — Wikimedia contact email

    When absent, providers fall back to TRIO_*_KEY env vars on the host.
    """
    set_request_keys(RequestKeys(
        sec_ua=request.headers.get("X-TRIO-SEC-UA"),
        fmp_key=request.headers.get("X-TRIO-FMP-KEY"),
        wiki_ua=request.headers.get("X-TRIO-WIKI-UA"),
    ))
    try:
        response = await call_next(request)
    finally:
        reset_request_keys()
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/byok/status")
def byok_status(request: Request) -> dict:
    """Tell the client which BYOK keys arrived on this request. Used by the
    Settings UI to show 'live mode active' vs 'demo mode' badges. Never
    returns the key itself — only a boolean per slot."""
    h = request.headers
    sec = bool(h.get("X-TRIO-SEC-UA"))
    fmp = bool(h.get("X-TRIO-FMP-KEY"))
    wiki = bool(h.get("X-TRIO-WIKI-UA"))
    has_any = sec or fmp or wiki
    return {
        "live_mode": has_any,
        "providers": {
            "sec_edgar": sec,
            "financial_modeling_prep": fmp,
            "wikipedia": wiki,
        },
        "coverage": {
            "altman_z": sec,
            "dvd_yld_ind": sec,
            "vol_avg_3m": True,            # yfinance — no key needed
            "target_return": fmp,
            "analyst_sent": fmp,
            "insider_flow": sec,           # Form 4 via EDGAR
            "retail_flow": wiki,
        },
    }


@app.get("/models")
def list_models() -> dict:
    return {
        "rba": [
            {"id": "bos", "version": "rba-bos-1.0.0", "label": "5-Factor Buy-or-Sell"},
            {"id": "bos_flow", "version": "rba-bos-flow-1.0.0", "label": "7-Factor BOS-Flow (BOS + insider + retail)"},
            {"id": "qv", "version": "rba-qv-1.0.0", "label": "Quality-Value (Greenblatt + Novy-Marx)"},
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
    if model == "bos_flow":
        return score_bos_flow(
            req.rows, universe=req.universe, weights=req.bos_flow_weights,
        )
    if model == "qv":
        return score_qv(
            req.rows, universe=req.universe, weights=req.qv_weights,
        )
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


class SimulateRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    fundamental_anchor: float = Field(default=1.0, ge=0.1, le=10.0,
                                      description="1.0 = fairly valued; >1 = overvalued")
    initial_sentiment_z: float = Field(default=0.0, ge=-5.0, le=10.0,
                                       description="initial retail attention z-score")
    n_steps: int = Field(default=30, ge=5, le=200)
    seed: int = Field(default=42)


@app.post("/simulate")
def simulate(req: SimulateRequest) -> dict:
    """MIROFISH agent-based shock simulator.

    Two-faction swarm (retail + institutional) projects price action over
    N steps in response to a fundamental shock. Returns the price path,
    peak-deviation, and a contagion score in [0, 1].

    This is a v0 scaffold — see docs/algorithms/mirofish.md for the
    research roadmap (ATLAS-GIC graph, Soros reflexivity, Darwinian
    weighting). Today it gives interpretable numbers on a single ticker.
    """
    result = simulate_shock(
        ticker=req.ticker,
        fundamental_anchor=req.fundamental_anchor,
        initial_sentiment_z=req.initial_sentiment_z,
        n_steps=req.n_steps,
        seed=req.seed,
    )
    return {
        "ticker": result.ticker,
        "n_steps": result.n_steps,
        "initial_price": result.initial_price,
        "final_price": round(result.final_price, 2),
        "price_path": [round(p, 2) for p in result.price_path],
        "peak_deviation_pct": result.peak_deviation_pct,
        "fundamental_anchor": result.fundamental_anchor,
        "institutional_share": result.institutional_share,
        "contagion_score": result.contagion_score,
        "warnings": result.warnings,
    }


@app.get("/universes")
def universes() -> dict:
    """Curated equity universes the UI can prefill. Each entry carries the
    full ticker list so the client can populate its textarea in one click.

    Coverage indicator: "us" universes get full 7-factor PIT (when keys are
    present); "my" universes get only the price-based factors today —
    EDGAR/FMP don't cover Bursa, and English Wikipedia coverage of KLCI
    names is patchy. See `docs/algorithms/universes.md`.
    """
    return {
        "universes": [
            {
                "id": u.id,
                "label": u.label,
                "snapshot": u.snapshot,
                "coverage": u.coverage,
                "n": len(u.tickers),
                "tickers": u.tickers,
            }
            for u in ALL_UNIVERSES.values()
        ],
    }


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
    """Pick the PIT provider at startup via ``TRIO_PIT_PROVIDER`` env.

    Options:
    - ``mock``   (default) — MockPitProvider, deterministic synthetic.
    - ``edgar``  — real SEC EDGAR adapter (3 of 5 BOS factors, US-only).
                   Requires ``TRIO_SEC_UA`` env (contact email).
    - ``edgar+fmp`` — Merged EDGAR + Financial Modeling Prep → all 5 BOS
                     factors PIT-honest. Requires ``TRIO_SEC_UA`` and
                     ``TRIO_FMP_KEY`` env vars.
    - ``fmp``    — FMP only (analyst factors only; vol_avg_3m & altman_z
                   stay None). Mostly useful for testing the FMP wiring.
    """
    import os
    choice = os.environ.get("TRIO_PIT_PROVIDER", "mock").lower()
    if choice == "all":  # full stack: edgar + fmp + insider + retail
        edgar = EdgarPitProvider()
        return MergedPitProvider([
            edgar, FmpPitProvider(),
            InsiderFlowPitProvider(edgar_pit=edgar),
            RetailFlowPitProvider(),
        ])
    if choice == "edgar+fmp+insider":
        edgar = EdgarPitProvider()
        return MergedPitProvider([
            edgar, FmpPitProvider(), InsiderFlowPitProvider(edgar_pit=edgar),
        ])
    if choice == "edgar+insider":
        edgar = EdgarPitProvider()
        return MergedPitProvider([edgar, InsiderFlowPitProvider(edgar_pit=edgar)])
    if choice == "edgar+fmp":
        return MergedPitProvider([EdgarPitProvider(), FmpPitProvider()])
    if choice == "edgar":
        return EdgarPitProvider()
    if choice == "fmp":
        return FmpPitProvider()
    if choice == "insider":
        return InsiderFlowPitProvider()
    if choice == "retail":
        return RetailFlowPitProvider()
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
