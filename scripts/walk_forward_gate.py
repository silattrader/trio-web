"""Walk-forward MLA gate evaluation.

For each rolling OOS window, retrain MLA on all data BEFORE the window,
then run the promotion gate on the window itself. Aggregates win-rate
and dispersion across windows so we can distinguish "MLA actually beats
RBA consistently" from "MLA got lucky on one slice."

Usage: ``py -3.12 scripts/walk_forward_gate.py``
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
from trio_algorithms.mla.promote import run_gate

ARTIFACT_DIR = Path("packages/algorithms/trio_algorithms/mla/artifacts/walk_forward")
DATA_START = date(2018, 1, 1)

# Quarterly OOS windows from 2021 onward — first window starts after we have
# enough training data. Each window: roughly 6 months of testing.
WINDOWS: list[tuple[date, date]] = [
    (date(2021, 1, 4),  date(2021, 6, 30)),   # H1 2021 — bull
    (date(2021, 7, 1),  date(2021, 12, 31)),  # H2 2021 — peak
    (date(2022, 1, 3),  date(2022, 6, 30)),   # H1 2022 — bear / rate-shock
    (date(2022, 7, 1),  date(2022, 12, 30)),  # H2 2022 — capitulation
    (date(2023, 1, 3),  date(2023, 6, 30)),   # H1 2023 — bottom-and-bounce
    (date(2023, 7, 3),  date(2023, 12, 29)),  # H2 2023 — AI rally
]


@dataclass
class WindowResult:
    test_start: date
    test_end: date
    n_train: int
    train_r2: float
    rba_cagr: float
    mla_cagr: float
    rba_sharpe: float
    mla_sharpe: float
    rba_total: float
    mla_total: float
    cagr_lift: float
    sharpe_lift: float
    promote: bool


def train_for_window(train_start: date, train_end: date) -> tuple[Path, int, float]:
    """Train an MLA artifact on data in [train_start, train_end]. Returns
    (artifact_path, n_samples, train_r2)."""
    cache = ARTIFACT_DIR / f"pit_{train_start.isoformat()}_{train_end.isoformat()}.pkl"
    samples = build_pit_dataset(start=train_start, end=train_end, cache_path=cache)
    X, y, _kept = to_xy(samples)
    if len(X) < 30:
        raise RuntimeError(
            f"Only {len(X)} samples for {train_start}..{train_end} — refusing to train."
        )
    model = GradientBoostingRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42,
    )
    model.fit(X, y)
    preds = model.predict(X)
    r2 = float(r2_score(y, preds))
    hit = float(np.mean(np.sign(preds) == np.sign(y)))
    art = ARTIFACT_DIR / f"mla_{train_end.isoformat()}.joblib"
    art.parent.mkdir(parents=True, exist_ok=True)
    MlaScorer(model=model, meta=TrainingMeta(
        n_samples=len(X), train_r2=r2, rba_corr=hit,
    )).save(art)
    return art, len(X), r2


def run_window(test_start: date, test_end: date) -> WindowResult:
    """Train on everything before test_start, evaluate on the test window."""
    artifact, n_train, train_r2 = train_for_window(
        DATA_START, date.fromordinal(test_start.toordinal() - 1),
    )
    rba, mla, decision = run_gate(
        start=test_start, end=test_end, artifact=artifact,
        top_n=5, rebalance_days=63,
    )
    return WindowResult(
        test_start=test_start, test_end=test_end,
        n_train=n_train, train_r2=train_r2,
        rba_cagr=rba.metrics.cagr, mla_cagr=mla.metrics.cagr,
        rba_sharpe=rba.metrics.sharpe, mla_sharpe=mla.metrics.sharpe,
        rba_total=rba.metrics.total_return, mla_total=mla.metrics.total_return,
        cagr_lift=decision.cagr_lift, sharpe_lift=decision.sharpe_lift,
        promote=decision.promote,
    )


def main() -> None:
    print("Walk-forward MLA gate evaluation")
    print(f"Data start: {DATA_START}  ·  {len(WINDOWS)} OOS windows")
    print("=" * 78)
    print(
        f"{'Window':<22s}  {'N_train':>7s}  {'r2':>5s}  "
        f"{'RBA':>7s}  {'MLA':>7s}  {'Lift':>7s}  {'Promote':>7s}"
    )
    print("-" * 78)

    results: list[WindowResult] = []
    for ts, te in WINDOWS:
        try:
            r = run_window(ts, te)
        except Exception as e:  # noqa: BLE001
            print(f"{ts} -> {te}  FAILED: {e}")
            continue
        results.append(r)
        print(
            f"{ts.isoformat()}->{te.strftime('%m-%d')}  "
            f"{r.n_train:>7d}  {r.train_r2:>5.2f}  "
            f"{r.mla_total - r.rba_total:+7.2%}  "
            f"{r.mla_cagr:>+7.2%}  "
            f"{r.cagr_lift:>+7.2%}  "
            f"{'YES' if r.promote else 'no':>7s}"
        )

    if not results:
        print("No windows succeeded.")
        return

    print("=" * 78)
    cagr_lifts = [r.cagr_lift for r in results]
    sharpe_lifts = [r.sharpe_lift for r in results]
    n_promote = sum(1 for r in results if r.promote)
    n_mla_better = sum(1 for r in results if r.cagr_lift > 0)

    print("Aggregate (across windows):")
    print(f"  Mean CAGR lift     : {stats.mean(cagr_lifts):+7.2%}")
    print(f"  Median CAGR lift   : {stats.median(cagr_lifts):+7.2%}")
    print(f"  Stdev CAGR lift    : {stats.stdev(cagr_lifts) if len(cagr_lifts)>1 else 0:>7.2%}")
    print(f"  Mean Sharpe lift   : {stats.mean(sharpe_lifts):+5.2f}")
    print(f"  MLA beat RBA in    : {n_mla_better}/{len(results)} windows ({n_mla_better/len(results):.0%})")
    print(f"  Gate would promote : {n_promote}/{len(results)} windows ({n_promote/len(results):.0%})")
    print("-" * 78)
    if n_promote >= len(results) * 0.66 and stats.mean(cagr_lifts) > 0:
        print("VERDICT: MLA-7-factor consistently beats RBA-BOS-Flow across windows.")
    elif n_promote == 0:
        print("VERDICT: MLA-7-factor never beats RBA-BOS-Flow. Architecture works,")
        print("         but this universe + horizon doesn't reward the model.")
    else:
        print("VERDICT: Mixed. MLA wins some windows, loses others. Single-window")
        print("         claims (e.g. the prior 'gate PASSES' result) are not robust.")


if __name__ == "__main__":  # pragma: no cover
    main()
