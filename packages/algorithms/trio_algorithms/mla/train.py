"""Training script for MLA v0.

Synthesises a labelled dataset where the label is the BOS final_score plus a
non-linear "alpha" term that simulates the kind of interaction effect a
linear weighted-sum cannot capture:

    label = bos(row) + 0.6 * 1{altman_z > 2 AND dvd_yld > 4}
                     - 0.5 * 1{altman_z < 1 AND target_return < 0}
                     + N(0, 0.15)

The model learns this composite. In production, this synthetic loop is
replaced by real PIT factor history (Path 3) joined with realised
forward-period returns. Until then, the architecture is real and the
plumbing is exercised end-to-end — the *labels* are admittedly synthetic.

CLI: ``python -m trio_algorithms.mla.train --out path/to/model.joblib``
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import r2_score

from ..rba.bos import score_bos
from .model import FEATURE_ORDER, MlaScorer, TrainingMeta

DEFAULT_N = 5_000
DEFAULT_SEED = 42


def _synth_row(rng: random.Random) -> dict:
    """Sample one synthetic factor row across realistic-ish ranges."""
    return {
        "ticker": "T",
        "vol_avg_3m": rng.uniform(50_000, 3_000_000),
        "target_return": rng.gauss(8, 12),
        "dvd_yld_ind": max(0.0, rng.gauss(3.5, 2.5)),
        "altman_z": max(0.2, rng.gauss(2.0, 1.0)),
        "analyst_sent": min(5.0, max(1.0, rng.gauss(3.5, 0.7))),
    }


def _alpha_term(row: dict) -> float:
    """Non-linear edge that BOS's weighted-sum cannot capture."""
    bonus = 0.0
    if row["altman_z"] > 2 and row["dvd_yld_ind"] > 4:
        bonus += 0.6
    if row["altman_z"] < 1 and row["target_return"] < 0:
        bonus -= 0.5
    return bonus


def build_dataset(n: int, seed: int) -> tuple[np.ndarray, np.ndarray, list[float]]:
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    rows = [_synth_row(rng) for _ in range(n)]
    bos_resp = score_bos(rows, universe="SYNTH_TRAIN")
    bos_scores = [r.final_score or 0.0 for r in bos_resp.results]
    alpha = np.array([_alpha_term(r) for r in rows])
    noise = nrng.normal(0, 0.15, size=n)
    y = np.array(bos_scores) + alpha + noise
    X = np.array([[r[k] for k in FEATURE_ORDER] for r in rows], dtype=float)
    return X, y, bos_scores


def train(n_samples: int = DEFAULT_N, seed: int = DEFAULT_SEED) -> MlaScorer:
    X, y, bos_scores = build_dataset(n_samples, seed)
    model = GradientBoostingRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05, random_state=seed,
    )
    model.fit(X, y)
    preds = model.predict(X)
    train_r2 = float(r2_score(y, preds))
    # Correlation between MLA preds and RBA scores on training data — should be
    # high (same factors) but not 1.0 (alpha term diverges).
    rba_corr = float(np.corrcoef(preds, bos_scores)[0, 1])
    meta = TrainingMeta(n_samples=n_samples, train_r2=train_r2, rba_corr=rba_corr)
    return MlaScorer(model=model, meta=meta)


def train_real_pit(
    *,
    cache_path: Path | None = None,
    seed: int = DEFAULT_SEED,
) -> tuple[MlaScorer, dict]:
    """Train on real EDGAR-PIT factors → realised forward returns.

    Returns (scorer, info-dict). The scorer's TrainingMeta carries the
    train r2 vs forward returns; the info-dict carries n_kept, n_dropped,
    feature coverage, and the date range — useful for the README + UI.

    Network-heavy on cold cache; cache the dataset via `cache_path`.
    """
    from .data_pipeline import build_pit_dataset, to_xy

    samples = build_pit_dataset(cache_path=cache_path)
    X, y, kept = to_xy(samples)
    if len(X) < 50:
        raise RuntimeError(
            f"Only {len(X)} usable samples after filtering — cannot train. "
            "Likely an EDGAR coverage issue (too many altman_z=None)."
        )

    model = GradientBoostingRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05, random_state=seed,
    )
    model.fit(X, y)
    preds = model.predict(X)
    train_r2 = float(r2_score(y, preds))

    # No analytic RBA correlation here — y is a forward return, not a BOS
    # score. Surface a different signal: directional hit rate (preds and
    # actuals have the same sign).
    sign_hit = float(np.mean(np.sign(preds) == np.sign(y)))

    meta = TrainingMeta(
        n_samples=len(X), train_r2=train_r2, rba_corr=sign_hit,
    )
    info = {
        "n_kept": len(X),
        "n_dropped": len(samples) - len(X),
        "tickers": sorted({s.ticker for s in kept}),
        "date_range": (
            min(s.as_of for s in kept).isoformat() if kept else None,
            max(s.as_of for s in kept).isoformat() if kept else None,
        ),
        "directional_hit_rate": sign_hit,
    }
    return MlaScorer(model=model, meta=meta), info


def main() -> None:  # pragma: no cover (CLI)
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--real", action="store_true",
                   help="Train on real EDGAR-PIT factors (network-heavy first run)")
    p.add_argument("--cache", type=Path, default=None,
                   help="Cache the materialised dataset to this path")
    p.add_argument("--n", type=int, default=DEFAULT_N)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = p.parse_args()
    if args.real:
        scorer, info = train_real_pit(cache_path=args.cache, seed=args.seed)
        scorer.save(args.out)
        print(f"Wrote {args.out}  ·  r2={scorer.meta.train_r2:.3f}  hit_rate={scorer.meta.rba_corr:.3f}")
        print(f"  samples kept: {info['n_kept']}  dropped: {info['n_dropped']}")
        print(f"  tickers: {len(info['tickers'])}  range: {info['date_range']}")
    else:
        scorer = train(args.n, args.seed)
        scorer.save(args.out)
        print(f"Wrote {args.out}  ·  r2={scorer.meta.train_r2:.3f}  rba_corr={scorer.meta.rba_corr:.3f}")


if __name__ == "__main__":  # pragma: no cover
    main()
