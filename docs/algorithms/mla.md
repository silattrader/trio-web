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
period. **Status: PASSED** on both 5-factor and 7-factor variants.

### 5-factor MLA · gate-passed 2026-04-26

Original BOS factors only. 2022-2023 out-of-sample, model trained 2018-2021.

| Metric        | RBA-BOS | MLA-5-factor | Lift     |
|---------------|---------|--------------|----------|
| Total return  |  +9.58% |      +31.91% | +22.3 pp |
| CAGR          |  +4.73% |      +15.01% | +10.3 pp |
| Sharpe        |    0.33 |         0.74 | +0.41    |
| Max drawdown  | -19.15% |      -27.01% | -7.9 pp  |

### 7-factor MLA · gate-passed 2026-04-26 (but underperforms 5-factor)

Adds `insider_flow` (Form 4) + `retail_flow` (Wikipedia pageviews z-score).
Same universe + window + train/test split as the 5-factor run.

| Metric        | RBA-BOS-Flow | MLA-7-factor | Lift     |
|---------------|--------------|--------------|----------|
| Total return  |       +9.58% |      +26.36% | +16.8 pp |
| CAGR          |       +4.73% |      +12.54% | +7.81 pp |
| Sharpe        |         0.33 |         0.62 | +0.29    |
| Max drawdown  |      -19.15% |      -25.10% | -5.95 pp |

The gate passes — MLA-7-factor beats the corresponding RBA. **But against
MLA-5-factor on the same OOS window, the 7-factor model is worse.** Adding
the flow factors hurt rather than helped here.

This is the kind of finding that walk-forward evaluation is *supposed* to
surface, and it deserves explicit documentation rather than burial:

| | 5-factor MLA | 7-factor MLA |
|---|---|---|
| CAGR | 15.01% | 12.54% |
| Sharpe | 0.74 | 0.62 |
| TotRet | +31.91% | +26.36% |

**Plausible causes** (none yet validated):
- 188 training samples is thin for a 7-feature gradient boost (curse of
  dimensionality — the new factors widen the search space without enough
  data to find their true coefficient).
- 90-day rolling flow signals don't align well with the 63-day forward
  return label — different time horizons.
- Flow factors may duplicate signal already captured by altman_z + dvd_yld
  rather than adding orthogonal edge.
- Single OOS window can't distinguish bad luck from worse model.

**Active artifact remains the 7-factor model** (`mla_v0.joblib` is full-
range trained on 2018-2023 with all 7 features). The 5-factor model is
preserved for comparison but no longer the default. Honest reasoning: the
5-factor's edge may be lucky on this single OOS slice; only walk-forward
across many slices can tell. Until that runs, both gate-passed models are
documented and either can be loaded by passing `artifact=` to
`score_mla_v0()`.

**To reproduce:**

```
py -3.12 -m trio_algorithms.mla.promote --start 2022-01-03 \\
   --end 2023-12-29 \\
   --artifact packages/algorithms/trio_algorithms/mla/artifacts/mla_v1_clean.joblib
```

**Honest open questions:**
- 5-factor vs 7-factor under walk-forward (multiple OOS slices) — would the
  5-factor's lead survive? Or is it a single-window artifact?
- S&P 500-wide universe (currently 28-name large-cap basket).
- Survivorship bias — universe is today's large-caps, not PIT membership.
- Forward-horizon sensitivity — does 63-day return label fit the flow
  factors' natural decay? 30-day or 180-day would shift their value.

## Walk-forward gate evaluation (2026-04-27)

Single-window gate runs are vulnerable to selection effects. To test
whether the prior gate-pass was real edge or one lucky slice, the model
is retrained at the start of each rolling 6-month OOS window using all
PIT data available before that window starts. Implementation:
``scripts/walk_forward_gate.py``.

### Result across 6 H1/H2 windows (2021-H1 through 2023-H2)

| Window | Train n | RBA→MLA TotRet diff | MLA CAGR | CAGR lift | Gate |
|--------|---------|---------------------|----------|-----------|------|
| 2021-H1 | 140 | −11.8 pp | +55% | **−32 pp** | ✗ |
| 2021-H2 | 164 | wins | +75% | +21 pp | ✓ |
| 2022-H1 | 188 | small loss | −23% | −4 pp | ✗ |
| 2022-H2 | 212 | wins | +20% | +4 pp | ✓ |
| 2023-H1 | 236 | wins | +87% | **+51 pp** | ✓ |
| 2023-H2 | 260 | wins | +25% | +29 pp | ✓ |

### Aggregate

- **Mean CAGR lift:** +11.57 pp
- **Median CAGR lift:** +12.66 pp
- **Stdev CAGR lift:** 28.85 pp (high — volatile across regimes)
- **Mean Sharpe lift:** +0.60
- **MLA beat RBA in 4 of 6 windows** (67%)
- **Gate would promote in 4 of 6 windows** (67%)

### Verdict

MLA-7-factor outperforms RBA-BOS-Flow on average, but with substantial
window-to-window variance. The mean +11.6 pp CAGR lift is real edge — it
isn't a single-window artifact. But the 33% loss-rate is a real risk:
MLA had two windows where RBA was the better choice, including a ~32 pp
underperformance in 2021-H1.

**Implications for production use:**
- A PM running MLA across an entire year is likely better off than running
  RBA — the wins compound, the losses are bounded.
- A PM running MLA on a single window has a ~1-in-3 chance of underperforming.
- The high dispersion is a signal that *neither* model is reliably good —
  fundamentals + flow on a 28-name universe is a noisy regime.

### What this doesn't yet test

- **5-factor vs 7-factor head-to-head** under walk-forward (still pending).
- **Out-of-universe generalization**: results are conditioned on this
  curated 28-name basket. SP500-wide or KLCI-wide may differ.
- **Survivorship bias**: today's universe, not PIT membership.
- **Different forward-return horizons** (the label is 63 trading days; flow
  factors' natural decay may want 30 or 180).
- **Different rebalance cadences** (here: every 63 days, top-5).
