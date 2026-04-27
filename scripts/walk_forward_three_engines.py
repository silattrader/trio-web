"""Three-engine walk-forward head-to-head: BOS-Flow vs QV vs MLA-7-factor.

Each rolling 6-month OOS window runs the rba_pit strategy three ways:
- score_fn=score_bos_flow (canonical 7-factor weighted)
- score_fn=score_qv         (Greenblatt + Novy-Marx + Graham — NEW)
- score_fn=score_mla_v0     (gradient-boosted, retrained per window)

The QV engine consumes the new EDGAR-emitted fields (roe, gp/a, d/e,
earnings_yield, book_to_market, fcf_yield) added 2026-04-28.

Output: a per-window comparison + aggregate stats.
"""
from __future__ import annotations

import statistics as stats
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import r2_score

from trio_algorithms.mla.data_pipeline import build_pit_dataset, to_xy
from trio_algorithms.mla.model import MlaScorer, TrainingMeta

ARTIFACT_DIR = Path("packages/algorithms/trio_algorithms/mla/artifacts/walk_forward")
DATA_START = date(2018, 1, 1)
RANDOM_SEED = 42

WINDOWS: list[tuple[date, date]] = [
    (date(2021, 1, 4),  date(2021, 6, 30)),
    (date(2021, 7, 1),  date(2021, 12, 31)),
    (date(2022, 1, 3),  date(2022, 6, 30)),
    (date(2022, 7, 1),  date(2022, 12, 30)),
    (date(2023, 1, 3),  date(2023, 6, 30)),
    (date(2023, 7, 3),  date(2023, 12, 29)),
]


@dataclass
class WindowOutcome:
    test_start: date
    test_end: date
    bos_flow_cagr: float
    qv_cagr: float
    mla_cagr: float
    bos_flow_sharpe: float
    qv_sharpe: float
    mla_sharpe: float


def train_mla_for_window(train_start: date, train_end: date) -> Path:
    cache = ARTIFACT_DIR / f"pit_{train_start.isoformat()}_{train_end.isoformat()}.pkl"
    samples = build_pit_dataset(start=train_start, end=train_end, cache_path=cache)
    X, y, _ = to_xy(samples)
    if len(X) < 30:
        raise RuntimeError(f"only {len(X)} samples for {train_start}..{train_end}")
    model = GradientBoostingRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05, random_state=RANDOM_SEED,
    )
    model.fit(X, y)
    r2 = float(r2_score(y, model.predict(X)))
    hit = float(np.mean(np.sign(model.predict(X)) == np.sign(y)))
    art = ARTIFACT_DIR / f"mla_h2h_{train_end.isoformat()}.joblib"
    art.parent.mkdir(parents=True, exist_ok=True)
    MlaScorer(model=model, meta=TrainingMeta(
        n_samples=len(X), train_r2=r2, rba_corr=hit,
    )).save(art)
    return art


def run_window(test_start: date, test_end: date) -> WindowOutcome:
    from trio_backtester import BacktestRequest, run_backtest
    from trio_backtester.data import fetch_history, fetch_volume_history
    from trio_algorithms.rba.bos_flow import score_bos_flow
    from trio_algorithms.rba.qv import score_qv
    from trio_algorithms.mla.inference import score_mla_v0
    from trio_algorithms.mla.data_pipeline import DEFAULT_UNIVERSE
    from trio_data_providers import (
        EdgarPitProvider, InsiderFlowPitProvider, MergedPitProvider,
        RetailFlowPitProvider,
    )

    train_end = date.fromordinal(test_start.toordinal() - 1)
    print(f"  training MLA on [{DATA_START.isoformat()}..{train_end.isoformat()}]")
    artifact = train_mla_for_window(DATA_START, train_end)

    universe = DEFAULT_UNIVERSE
    print(f"  fetching prices+volumes for {test_start}..{test_end}")
    _, prices = fetch_history(universe, test_start, test_end)
    volumes = fetch_volume_history(universe, test_start, test_end)
    dates = sorted({d for s in prices.values() for d in s})

    edgar = EdgarPitProvider()
    pit = MergedPitProvider([
        edgar, InsiderFlowPitProvider(edgar_pit=edgar), RetailFlowPitProvider(),
    ])

    def make_score_fn(scorer_callable):
        def _fn(tickers, _model_name, as_of):
            res = pit.fetch_as_of(
                tickers, as_of=as_of, model="qv",
                prices=prices, volumes=volumes,
            )
            return scorer_callable(res.rows, universe=f"PIT@{as_of.isoformat()}")
        return _fn

    def mla_score_fn(tickers, _model_name, as_of):
        res = pit.fetch_as_of(
            tickers, as_of=as_of, model="bos_flow",
            prices=prices, volumes=volumes,
        )
        return score_mla_v0(res.rows, universe=f"PIT@{as_of.isoformat()}", artifact=artifact)

    req = BacktestRequest(
        tickers=universe, start=test_start, end=test_end,
        top_n=5, rebalance_days=63, fee_bps=5.0,
    )

    print("  backtesting BOS-Flow")
    bos_flow_bt = run_backtest(
        req, "rba_pit", history=prices, dates=dates,
        score_fn=make_score_fn(score_bos_flow),
    )
    print("  backtesting QV (NEW)")
    qv_bt = run_backtest(
        req, "rba_pit", history=prices, dates=dates,
        score_fn=make_score_fn(score_qv),
    )
    print("  backtesting MLA-7-factor")
    mla_bt = run_backtest(
        req, "rba_pit", history=prices, dates=dates,
        score_fn=mla_score_fn,
    )

    return WindowOutcome(
        test_start=test_start, test_end=test_end,
        bos_flow_cagr=bos_flow_bt.metrics.cagr,
        qv_cagr=qv_bt.metrics.cagr,
        mla_cagr=mla_bt.metrics.cagr,
        bos_flow_sharpe=bos_flow_bt.metrics.sharpe,
        qv_sharpe=qv_bt.metrics.sharpe,
        mla_sharpe=mla_bt.metrics.sharpe,
    )


def main() -> None:
    print("Three-engine walk-forward: BOS-Flow vs QV vs MLA-7")
    print(f"Universe: 28-name curated US large caps  ·  {len(WINDOWS)} OOS windows")
    print("=" * 90)

    outcomes: list[WindowOutcome] = []
    for ts, te in WINDOWS:
        print(f"\n=== Window {ts} -> {te} ===")
        try:
            outcomes.append(run_window(ts, te))
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {e}")

    if not outcomes:
        print("No windows succeeded.")
        return

    print("\n" + "=" * 90)
    print(f"{'Window':<22s}  {'BOS-Flow':>10s}  {'QV':>10s}  {'MLA-7':>10s}  {'QV-Flow':>10s}  {'QV-MLA':>10s}")
    print("-" * 90)
    for o in outcomes:
        print(
            f"{o.test_start} {o.test_end.strftime('%m-%d')}  "
            f"{o.bos_flow_cagr:>+10.2%}  "
            f"{o.qv_cagr:>+10.2%}  "
            f"{o.mla_cagr:>+10.2%}  "
            f"{o.qv_cagr - o.bos_flow_cagr:>+10.2%}  "
            f"{o.qv_cagr - o.mla_cagr:>+10.2%}"
        )

    print("=" * 90)
    cagr_bf = [o.bos_flow_cagr for o in outcomes]
    cagr_qv = [o.qv_cagr for o in outcomes]
    cagr_mla = [o.mla_cagr for o in outcomes]
    n_qv_beats_bf = sum(1 for o in outcomes if o.qv_cagr > o.bos_flow_cagr)
    n_qv_beats_mla = sum(1 for o in outcomes if o.qv_cagr > o.mla_cagr)
    n_qv_beats_both = sum(
        1 for o in outcomes
        if o.qv_cagr > o.bos_flow_cagr and o.qv_cagr > o.mla_cagr
    )

    print("\nAggregate (across windows):")
    print(f"  Mean CAGR BOS-Flow : {stats.mean(cagr_bf):+7.2%}")
    print(f"  Mean CAGR QV       : {stats.mean(cagr_qv):+7.2%}")
    print(f"  Mean CAGR MLA-7    : {stats.mean(cagr_mla):+7.2%}")
    print(f"  QV beats BOS-Flow  : {n_qv_beats_bf}/{len(outcomes)} ({n_qv_beats_bf/len(outcomes):.0%})")
    print(f"  QV beats MLA-7     : {n_qv_beats_mla}/{len(outcomes)} ({n_qv_beats_mla/len(outcomes):.0%})")
    print(f"  QV best of three   : {n_qv_beats_both}/{len(outcomes)} ({n_qv_beats_both/len(outcomes):.0%})")


if __name__ == "__main__":  # pragma: no cover
    main()
