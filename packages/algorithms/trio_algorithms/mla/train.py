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


def main() -> None:  # pragma: no cover (CLI)
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--n", type=int, default=DEFAULT_N)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = p.parse_args()
    scorer = train(args.n, args.seed)
    scorer.save(args.out)
    print(f"Wrote {args.out}  ·  r2={scorer.meta.train_r2:.3f}  rba_corr={scorer.meta.rba_corr:.3f}")


if __name__ == "__main__":  # pragma: no cover
    main()
