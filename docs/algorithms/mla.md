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

## Training

Two paths live in `train.py`:

### `train()` — synthetic baseline

`build_dataset(n, seed)` synthesises factor rows + a non-linear alpha term
BOS can't express. Useful for unit tests + first-run UX. r2 ≈ 0.94 in-sample.

### `train_real_pit()` — real EDGAR PIT factors → realised forward returns

`data_pipeline.build_pit_dataset()` walks a curated 28-stock US large-cap
universe over quarter-end snapshots from 2018-Q1 onward. For each
(ticker, snapshot):

- Pulls 4-of-5 BOS factors PIT-honestly via `EdgarPitProvider` + yfinance
  (vol_avg_3m, dvd_yld_ind, altman_z; analyst_sent + target_return are
  forward-looking and substituted as constant placeholders 3.0 / 0.0 — same
  values applied at inference time inside `score_mla_v0` so train and serve
  match exactly).
- Computes label = forward 63-trading-day return on adj-close.
- Caches the materialised dataset to a pickle so subsequent training runs
  skip the network.

CLI:

```
py -3.12 -m trio_algorithms.mla.train --real \
    --out packages/algorithms/trio_algorithms/mla/artifacts/mla_v0.joblib \
    --cache packages/algorithms/trio_algorithms/mla/artifacts/pit_dataset.pkl
```

Real-data run (2018-2023): 284 samples kept across 12 tickers (others dropped
for missing Altman-Z' — banks etc.), in-sample r2 ≈ 0.68, directional hit-rate
≈ 0.80. Honest signal of fit, not skill.

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

MLA cannot ship as default until backtested return ≥ RBA on same universe +
period. **Status: PASSED** as of 2026-04-26 on the curated 28-stock US
large-cap universe, 2022-2023 out-of-sample (model trained 2018-2021):

| Metric        | RBA-BOS | MLA v0  | Lift     |
|---------------|---------|---------|----------|
| Total return  |  +9.58% | +31.91% | +22.3 pp |
| CAGR          |  +4.73% | +15.01% | +10.3 pp |
| Sharpe        |    0.33 |    0.74 | +0.41    |
| Max drawdown  | -19.15% | -27.01% | -7.9 pp  |

CAGR + Sharpe gates both PASS. MaxDD is worse — the engine takes more risk
in exchange for the better returns. Acceptable given the gate thresholds
(CAGR lift ≥ 0, Sharpe lift ≥ -0.1) but flagged for the PM.

**To reproduce:** ``py -3.12 -m trio_algorithms.mla.promote --start 2022-01-03 \\
   --end 2023-12-29 --artifact .../mla_v1_clean.joblib``

**Not yet validated:** S&P 500-wide promotion (universe was 28 names),
multi-period robustness (only one OOS window), and effects of survivorship
bias (universe is today's large-caps, not point-in-time membership).
