"""5-factor vs 7-factor MLA — head-to-head walk-forward.

Settles the question raised by the prior gate runs: does adding insider_flow
and retail_flow as features actually help, or does the 5-factor model win?

For each rolling 6-month OOS window:
  1. Train MLA-5 on the first 5 columns (no flow factors) using all data
     before the window.
  2. Train MLA-7 on all 7 columns using the same data.
  3. Run rba_pit backtest with each model as the score_fn.
  4. Aggregate: head-to-head win-rate, mean-lift dispersion.

Bypasses ``score_mla_v0`` because it expects 7 features. We use the
sklearn model directly + a minimal ScoreResponse-shaped object that
``rba_pit.select_top_n_from_resp`` accepts.
"""
from __future__ import annotations

import statistics as stats
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import r2_score

from trio_algorithms.mla.data_pipeline import build_pit_dataset, to_xy

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

# 5-factor uses cols 0..4 (vol, target, dvd, altman, sent). 7-factor adds
# insider_flow + retail_flow.
FEATURES_5 = ["vol_avg_3m", "target_return", "dvd_yld_ind", "altman_z", "analyst_sent"]
FEATURES_7 = FEATURES_5 + ["insider_flow", "retail_flow"]


# --- minimal stand-ins that look like ScoreResponse / StockResult for
# rba_pit.select_top_n_from_resp. We don't need anything else — the
# strategy only reads .ticker and .final_score from each result.
@dataclass
class _LiteResult:
    ticker: str
    final_score: float | None


@dataclass
class _LiteResponse:
    results: list[_LiteResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def train_model(
    train_start: date, train_end: date, n_features: int,
) -> tuple[GradientBoostingRegressor, int, float]:
    """Train a GBM on data in [train_start, train_end] using the first
    ``n_features`` columns of the standard 7-feature row."""
    cache = ARTIFACT_DIR / f"pit_{train_start.isoformat()}_{train_end.isoformat()}.pkl"
    samples = build_pit_dataset(start=train_start, end=train_end, cache_path=cache)
    X, y, _ = to_xy(samples)
    if len(X) < 30:
        raise RuntimeError(f"only {len(X)} samples for {train_start}..{train_end}")
    X_subset = X[:, :n_features]
    model = GradientBoostingRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05, random_state=RANDOM_SEED,
    )
    model.fit(X_subset, y)
    r2 = float(r2_score(y, model.predict(X_subset)))
    return model, len(X), r2


def make_score_fn(model: GradientBoostingRegressor, n_features: int):
    """Wrap a fit GBM in a score_fn signature: (tickers, model_name, as_of)
    -> _LiteResponse. Pulls PIT rows for the universe at as_of via the
    same MergedPitProvider stack the production code uses."""
    from trio_data_providers import (
        EdgarPitProvider, InsiderFlowPitProvider, MergedPitProvider,
        RetailFlowPitProvider,
    )

    edgar = EdgarPitProvider()
    pit = MergedPitProvider([
        edgar, InsiderFlowPitProvider(edgar_pit=edgar), RetailFlowPitProvider(),
    ])

    # Same placeholder map as data_pipeline + inference, in feature-column order.
    placeholders = {
        "target_return": 0.0, "analyst_sent": 3.0,
        "insider_flow": 3.0, "retail_flow": 3.0,
    }
    feature_cols = FEATURES_7[:n_features]

    def _score(tickers, _model_name, as_of, prices, volumes):
        result = pit.fetch_as_of(
            tickers, as_of=as_of, model="bos",
            prices=prices, volumes=volumes,
        )
        rows = []
        out: list[_LiteResult] = []
        for r in result.rows:
            features = []
            ok = True
            for col in feature_cols:
                v = r.get(col)
                if v is None:
                    v = placeholders.get(col)
                if v is None:
                    ok = False
                    break
                try:
                    features.append(float(v))
                except (TypeError, ValueError):
                    ok = False
                    break
            if not ok or not features:
                out.append(_LiteResult(ticker=r["ticker"], final_score=None))
                continue
            x = np.asarray(features, dtype=float).reshape(1, -1)
            score = float(model.predict(x)[0])
            out.append(_LiteResult(ticker=r["ticker"], final_score=score))
            rows.append(r)
        return _LiteResponse(results=out, warnings=[])

    return _score


@dataclass
class WindowOutcome:
    test_start: date
    test_end: date
    n_train: int
    r2_5: float
    r2_7: float
    rba_cagr: float
    mla5_cagr: float
    mla7_cagr: float
    mla5_sharpe: float
    mla7_sharpe: float


def run_window(test_start: date, test_end: date) -> WindowOutcome:
    from trio_backtester import BacktestRequest, run_backtest
    from trio_backtester.data import fetch_history, fetch_volume_history
    from trio_algorithms.rba.bos_flow import score_bos_flow
    from trio_data_providers import (
        EdgarPitProvider, InsiderFlowPitProvider, MergedPitProvider,
        RetailFlowPitProvider,
    )
    from trio_algorithms.mla.data_pipeline import DEFAULT_UNIVERSE

    train_end = date.fromordinal(test_start.toordinal() - 1)
    print(f"  training [{DATA_START.isoformat()}..{train_end.isoformat()}]")
    m5, n_train, r2_5 = train_model(DATA_START, train_end, 5)
    m7, _, r2_7 = train_model(DATA_START, train_end, 7)
    print(f"    5-factor r2={r2_5:.3f}  ·  7-factor r2={r2_7:.3f}  ·  n={n_train}")

    universe = DEFAULT_UNIVERSE
    print(f"  fetching prices+volumes for {test_start}..{test_end}")
    _, prices = fetch_history(universe, test_start, test_end)
    volumes = fetch_volume_history(universe, test_start, test_end)
    dates = sorted({d for s in prices.values() for d in s})

    edgar = EdgarPitProvider()
    pit = MergedPitProvider([
        edgar, InsiderFlowPitProvider(edgar_pit=edgar), RetailFlowPitProvider(),
    ])

    def _rba_score_fn(tickers, _model_name, as_of):
        res = pit.fetch_as_of(
            tickers, as_of=as_of, model="bos_flow",
            prices=prices, volumes=volumes,
        )
        return score_bos_flow(res.rows, universe=f"PIT@{as_of.isoformat()}")

    fn5_inner = make_score_fn(m5, 5)
    fn7_inner = make_score_fn(m7, 7)

    def _wrap(inner):
        def _fn(tickers, model_name, as_of):
            return inner(tickers, model_name, as_of, prices, volumes)
        return _fn

    req = BacktestRequest(
        tickers=universe, start=test_start, end=test_end,
        top_n=5, rebalance_days=63, fee_bps=5.0,
    )
    print("  backtesting RBA-BOS-Flow")
    rba = run_backtest(req, "rba_pit", history=prices, dates=dates, score_fn=_rba_score_fn)
    print("  backtesting MLA-5-factor")
    bt5 = run_backtest(req, "rba_pit", history=prices, dates=dates, score_fn=_wrap(fn5_inner))
    print("  backtesting MLA-7-factor")
    bt7 = run_backtest(req, "rba_pit", history=prices, dates=dates, score_fn=_wrap(fn7_inner))

    return WindowOutcome(
        test_start=test_start, test_end=test_end,
        n_train=n_train, r2_5=r2_5, r2_7=r2_7,
        rba_cagr=rba.metrics.cagr,
        mla5_cagr=bt5.metrics.cagr,
        mla7_cagr=bt7.metrics.cagr,
        mla5_sharpe=bt5.metrics.sharpe,
        mla7_sharpe=bt7.metrics.sharpe,
    )


def main() -> None:
    print("Walk-forward 5-factor vs 7-factor MLA head-to-head")
    print(f"Universe: 28-name curated US large caps  ·  {len(WINDOWS)} OOS windows")
    print("=" * 84)

    outcomes: list[WindowOutcome] = []
    for ts, te in WINDOWS:
        print(f"\n=== Window {ts} -> {te} ===")
        try:
            outcomes.append(run_window(ts, te))
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {e}")

    if not outcomes:
        return

    print("\n" + "=" * 84)
    print(
        f"{'Window':<22s}  {'RBA':>7s}  {'MLA-5':>7s}  {'MLA-7':>7s}  "
        f"{'5-vs-7':>7s}  {'5-vs-RBA':>9s}  {'7-vs-RBA':>9s}"
    )
    print("-" * 84)
    for o in outcomes:
        print(
            f"{o.test_start} {o.test_end.strftime('%m-%d')}  "
            f"{o.rba_cagr:>+7.2%}  "
            f"{o.mla5_cagr:>+7.2%}  "
            f"{o.mla7_cagr:>+7.2%}  "
            f"{o.mla5_cagr - o.mla7_cagr:>+7.2%}  "
            f"{o.mla5_cagr - o.rba_cagr:>+9.2%}  "
            f"{o.mla7_cagr - o.rba_cagr:>+9.2%}"
        )

    print("=" * 84)
    lift_5 = [o.mla5_cagr - o.rba_cagr for o in outcomes]
    lift_7 = [o.mla7_cagr - o.rba_cagr for o in outcomes]
    five_vs_seven = [o.mla5_cagr - o.mla7_cagr for o in outcomes]
    n_5_wins = sum(1 for o in outcomes if o.mla5_cagr > o.mla7_cagr)
    n_5_beats_rba = sum(1 for o in outcomes if o.mla5_cagr > o.rba_cagr)
    n_7_beats_rba = sum(1 for o in outcomes if o.mla7_cagr > o.rba_cagr)

    print("\nAggregate (across windows):")
    print(f"  Mean lift 5-factor vs RBA  : {stats.mean(lift_5):+7.2%}")
    print(f"  Mean lift 7-factor vs RBA  : {stats.mean(lift_7):+7.2%}")
    print(f"  Mean 5-vs-7 differential   : {stats.mean(five_vs_seven):+7.2%}")
    print(f"  5-factor wins vs 7-factor  : {n_5_wins}/{len(outcomes)} ({n_5_wins/len(outcomes):.0%})")
    print(f"  5-factor beats RBA         : {n_5_beats_rba}/{len(outcomes)} ({n_5_beats_rba/len(outcomes):.0%})")
    print(f"  7-factor beats RBA         : {n_7_beats_rba}/{len(outcomes)} ({n_7_beats_rba/len(outcomes):.0%})")

    print("-" * 84)
    if stats.mean(five_vs_seven) > 0.02 and n_5_wins >= len(outcomes) * 0.66:
        print("VERDICT: 5-factor MLA outperforms 7-factor on this universe + horizon.")
        print("         Adding flow factors hurt across multiple regimes — keep them as")
        print("         architectural plumbing, but the 5-factor model is the production")
        print("         choice today. Open a follow-up: tune flow-factor windows / labels.")
    elif stats.mean(five_vs_seven) < -0.02 and n_5_wins <= len(outcomes) * 0.34:
        print("VERDICT: 7-factor MLA outperforms 5-factor — flow factors add real edge.")
    else:
        print("VERDICT: Inconclusive — mean differential is small relative to dispersion.")
        print("         5- and 7-factor are within noise; either is defensible.")


if __name__ == "__main__":  # pragma: no cover
    main()
