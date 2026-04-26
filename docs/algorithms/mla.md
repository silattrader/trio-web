# SOP — MLA v0 (P5)

**Source of truth:** `packages/algorithms/trio_algorithms/mla/`
**Endpoint:** `POST /score?model=mla_v0`

## North star

Prove the engine can be cleanly upgraded from rule-based to ML-based without
breaking the front end. Same `ScoreResponse` schema, same UI; the difference
is invisible to the client.

## Architecture

```
mla/
  __init__.py     # public surface
  model.py        # MlaScorer wrapper (sklearn GradientBoostingRegressor)
  train.py        # build_dataset() + train() + CLI
  inference.py    # score_mla_v0(rows, universe=) — matches RBA contract
  gate.py         # evaluate_promotion(mla_metrics, rba_metrics) → PromotionDecision
  artifacts/
    mla_v0.joblib # serialised model (joblib.dump tuple of (model, meta, FEATURE_ORDER))
```

## Inputs

The model reads the same 5 BOS factors per row:

```
vol_avg_3m, target_return, dvd_yld_ind, altman_z, analyst_sent
```

`FEATURE_ORDER` in `model.py` is the load-bearing constant — it is checked
against the saved artifact on load() and any drift refuses the model.

## Training (current state)

`train.py::build_dataset(n, seed)` synthesises factor rows, scores them with
RBA-BOS, then adds a non-linear "alpha" term that BOS's linear weighted-sum
cannot capture:

```python
label = bos(row)
      + 0.6 * 1{altman_z > 2 AND dvd_yld_ind > 4}
      - 0.5 * 1{altman_z < 1 AND target_return < 0}
      + N(0, 0.15)
```

This is intentionally synthetic. The labels are admittedly fake — the
production training loop will replace this with PIT factor history (see
`docs/algorithms/backtester.md` Path 3) joined to realised forward returns.
The architecture is real today; the training data is simulated.

CLI:

```
py -3.12 -m trio_algorithms.mla.train --out path/to/model.joblib --n 5000 --seed 42
```

Default training run produces r2 ≈ 0.94 on synthetic data, RBA-correlation
≈ 0.92 (high — same factors — but not 1.0, because of the alpha term).

## Inference

`score_mla_v0(rows, universe=, artifact=)`:

- Lazy-loads `artifacts/mla_v0.joblib` on first call; caches it process-wide.
- If the artifact is missing, trains a fresh in-memory model from a fixed
  seed and surfaces a warning. (Means tests + first-run UX work without a
  baked artifact, but production should always ship the artifact.)
- Returns a `ScoreResponse` with `model_version="mla-v0.1.0"`.
- `factors[].weight` carries `feature_importances_` per factor — the closest
  honest analogue to BOS factor weights for an explainability panel.

## Promotion gate

`gate.evaluate_promotion(mla_metrics, rba_metrics)` is the policy hook
between "MLA can be backtested" and "MLA can be exposed as the default
model". Defaults:

- CAGR lift ≥ 0 (MLA must not lose money relative to RBA)
- Sharpe lift ≥ -0.1 (small Sharpe trade tolerated for clear CAGR wins)

Both inputs must have `.cagr` and `.sharpe` attributes — `BacktestMetrics`
satisfies that. Returns `PromotionDecision(promote, cagr_lift, sharpe_lift,
reasons[])`. The reasons list is human-readable and is what the UI should
surface.

## Hard rule (from project_constitution)

MLA cannot ship to users until backtested return ≥ RBA on same universe +
period. Today MLA is exposed as a *preview* — selectable in the UI, callable
at `/score?model=mla_v0`, but it does not become the default until a real
PIT-trained artifact passes the promotion gate on KLCI + SP500.
