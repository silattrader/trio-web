"""MlaScorer — sklearn GradientBoostingRegressor over the 5 BOS factors.

The model takes raw factor values (vol_avg_3m, target_return, dvd_yld_ind,
altman_z, analyst_sent) and predicts a final_score in the same [0, 4]
band-scale as BOS. Trained on synthetic data that includes interaction
terms BOS's linear weighting cannot capture (e.g. "altman_z > 2 AND
dvd_yld > 4 → bonus") so MLA can demonstrably differ from RBA.

Inference is pure: load() once at module-import, score_one() per row.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

FEATURE_ORDER = [
    "vol_avg_3m",
    "target_return",
    "dvd_yld_ind",
    "altman_z",
    "analyst_sent",
    "insider_flow",
    "retail_flow",
]


@dataclass
class TrainingMeta:
    n_samples: int
    train_r2: float
    rba_corr: float  # how correlated MLA scores are with RBA on training data


class MlaScorer:
    """Wrapper around a fit GradientBoostingRegressor + metadata.

    Persistence: joblib.dump((self.model, self.meta, FEATURE_ORDER), path).
    """

    def __init__(self, model: GradientBoostingRegressor | None = None,
                 meta: TrainingMeta | None = None) -> None:
        self.model = model
        self.meta = meta

    @classmethod
    def load(cls, path: Path) -> "MlaScorer":
        bundle = joblib.load(path)
        model, meta, order = bundle
        if order != FEATURE_ORDER:
            raise ValueError(f"Model feature order {order} != current {FEATURE_ORDER}")
        return cls(model=model, meta=meta)

    def save(self, path: Path) -> None:
        if self.model is None:
            raise RuntimeError("Cannot save an unfit MlaScorer")
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump((self.model, self.meta, FEATURE_ORDER), path)

    def score_row(self, row: dict[str, Any]) -> float | None:
        """Predict one row's MLA score. Returns None if any feature is missing."""
        if self.model is None:
            raise RuntimeError("MlaScorer.score_row called on an unfit model")
        feats = []
        for k in FEATURE_ORDER:
            v = row.get(k)
            if v is None:
                return None
            try:
                feats.append(float(v))
            except (TypeError, ValueError):
                return None
        x = np.asarray(feats, dtype=float).reshape(1, -1)
        return float(self.model.predict(x)[0])

    def score_batch(self, rows: list[dict[str, Any]]) -> list[float | None]:
        return [self.score_row(r) for r in rows]
