"""SHAP analysis on the active MLA artifact.

Answers the open question from `docs/algorithms/mla.md`:
> Are insider_flow + retail_flow getting any model weight at all, or are
> they being ignored entirely?

Methodology:
  1. Load the production artifact (mla_v0.joblib — the 7-factor full-range
     model trained on 2018-2023 EDGAR + insider + retail PIT data).
  2. Build a representative explanation set from the cached PIT dataset
     (the same one the model was trained on; for SHAP we want a sample of
     the input distribution).
  3. Compute TreeExplainer SHAP values across that sample.
  4. Aggregate: mean |SHAP| per feature → ranked feature importance.

Output is plain-text (committed alongside the docs writeup); no plots
because we're shipping ASCII tables, not images.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
ARTIFACT = ROOT / "packages" / "algorithms" / "trio_algorithms" / "mla" / "artifacts" / "mla_v0.joblib"
DATASET = ROOT / "packages" / "algorithms" / "trio_algorithms" / "mla" / "artifacts" / "pit_dataset_v2.pkl"

# Quiet shap's tqdm + numba spam.
import warnings
warnings.filterwarnings("ignore")


def main() -> None:
    import joblib
    import shap

    print(f"Loading artifact:  {ARTIFACT.relative_to(ROOT)}")
    model, meta, feature_order = joblib.load(ARTIFACT)
    print(f"  trained on {meta.n_samples} samples · in-sample r2={meta.train_r2:.3f}")
    print(f"  features: {feature_order}")
    print()

    print(f"Loading PIT dataset for explanation set:  {DATASET.relative_to(ROOT)}")
    import pickle
    samples = pickle.loads(DATASET.read_bytes())
    print(f"  {len(samples)} PIT samples loaded")

    # Filter to samples with a label (forward_return) AND complete features —
    # same filter to_xy() applies during training.
    rows = []
    for s in samples:
        if s.forward_return is None:
            continue
        feats = []
        ok = True
        for k in feature_order:
            v = s.features.get(k)
            if v is None:
                ok = False
                break
            try:
                feats.append(float(v))
            except (TypeError, ValueError):
                ok = False
                break
        if ok:
            rows.append(feats)

    X = np.asarray(rows, dtype=float)
    print(f"  {len(X)} samples kept for SHAP analysis")
    print()

    print("Computing SHAP values via TreeExplainer...")
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)
    print(f"  shap_values shape: {shap_values.shape}")
    print()

    # Mean |SHAP| per feature — the standard global feature-importance metric.
    mean_abs = np.abs(shap_values).mean(axis=0)
    ranked = sorted(zip(feature_order, mean_abs), key=lambda x: -x[1])
    total = mean_abs.sum()
    if total <= 0:
        total = 1.0  # avoid div-by-zero in degenerate cases

    print("=" * 70)
    print("Mean |SHAP| per feature (global importance)")
    print("=" * 70)
    print(f"{'Rank':<5} {'Feature':<18} {'Mean |SHAP|':>14} {'% of total':>12} {'Bar':<20}")
    print("-" * 70)
    max_val = ranked[0][1] if ranked else 1.0
    for i, (name, val) in enumerate(ranked, 1):
        pct = val / total * 100
        bar_width = int(round(val / max_val * 20)) if max_val > 0 else 0
        bar = "#" * bar_width
        print(f"{i:<5} {name:<18} {val:>14.6f} {pct:>11.1f}% {bar}")
    print("=" * 70)
    print()

    # Compare BOS-classic features (cols 0-4) vs flow features (cols 5-6).
    bos_idx = [i for i, n in enumerate(feature_order) if n not in ("insider_flow", "retail_flow")]
    flow_idx = [i for i, n in enumerate(feature_order) if n in ("insider_flow", "retail_flow")]
    bos_share = mean_abs[bos_idx].sum() / total * 100
    flow_share = mean_abs[flow_idx].sum() / total * 100

    print(f"BOS-classic factors (5):   {bos_share:5.1f}% of total importance")
    print(f"Flow factors (insider+retail): {flow_share:5.1f}% of total importance")
    print()

    # Verdict
    if flow_share < 5:
        print("VERDICT: Flow factors carry <5% of model importance — the model is")
        print("         essentially 5-factor with noise on the new inputs.")
    elif flow_share < 15:
        print("VERDICT: Flow factors carry modest importance (5-15%) — they're")
        print("         being used but aren't drivers.")
    else:
        print("VERDICT: Flow factors are material drivers — keep + tune them.")


if __name__ == "__main__":
    main()
