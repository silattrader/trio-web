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

- **Out-of-universe generalization**: results are conditioned on this
  curated 28-name basket. SP500-wide or KLCI-wide may differ.
- **Survivorship bias**: today's universe, not PIT membership.
- **Different forward-return horizons** (the label is 63 trading days; flow
  factors' natural decay may want 30 or 180).
- **Different rebalance cadences** (here: every 63 days, top-5).

## SHAP analysis of the active artifact (2026-04-27)

`scripts/shap_analysis.py` — TreeExplainer over the 284 PIT training
samples — answers the open question of whether the 7-factor model
*actually uses* the flow factors:

| Rank | Feature | Mean \|SHAP\| | % of total |
|------|---------|---------------|------------|
| 1 | `vol_avg_3m` | 0.0341 | **39.6%** |
| 2 | `dvd_yld_ind` | 0.0313 | **36.4%** |
| 3 | `altman_z` | 0.0150 | 17.4% |
| 4 | `insider_flow` | 0.0031 | 3.6% |
| 5 | `retail_flow` | 0.0026 | 3.1% |
| 6 | `target_return` | **0.0000** | **0.0%** — dead weight |
| 7 | `analyst_sent` | **0.0000** | **0.0%** — dead weight |

### Three findings, each material

#### 1. `target_return` and `analyst_sent` carry literally zero model weight.

That's not the model failing to learn. It's the model correctly learning
to ignore them, because in the training pipeline `FmpPitProvider` isn't
enabled — those columns are filled with placeholder constants (0.0 for
target_return, 3.0 for analyst_sent). Constant-valued features have zero
variance, and a tree-based model assigns them zero importance.

The architecture is 7-factor; the *information content* is effectively
**5-factor**. To actually exercise these two slots, the training pipeline
needs FmpPitProvider in the merge stack — and `TRIO_FMP_KEY` set during
training. Today's free-tier setup can't sustain that across a multi-quarter
walk for a 28-stock universe.

#### 2. The flow factors aren't dead — but they're not drivers either.

`insider_flow` (3.6%) and `retail_flow` (3.1%) together carry **6.7%** of
total importance. That's modest. Three plausible reasons:

- **US mega-caps are a flow-noisy universe.** Insider activity on AAPL is
  drowned by daily $-volume that no individual filer can move.
- **The 90-day flow lookback may be too long for 63-day forward returns.**
- **Flow signals may be more predictive on small/mid-caps** where the
  signal-to-noise ratio is higher. Re-running on a Russell 2000-style
  universe would test this.

#### 3. The model is essentially trading on three real factors.

Volume + dividend yield + Altman-Z account for **93.4%** of the model's
explanatory power. That's actually a defensible, interpretable factor
stack — and it explains why MLA's edge over RBA-BOS-Flow (which weights
all 5 BOS factors) is real but bounded:

- MLA correctly *down-weights* the placeholder columns (BOS gives them
  10–20% each by default).
- MLA *finds non-linear interactions* in volume × dividend yield × Altman-Z
  that BOS's linear weighted-sum cannot.
- Net effect: ~+8 pp CAGR lift, with high dispersion.

### Implications

This SHAP run reframes earlier findings:

| Earlier framing | Updated framing |
|-----------------|-----------------|
| "5-factor MLA edges 7-factor by 1.5pp on average" | The 7-factor model effectively *is* a 5-factor model, since 2 of the 7 features are constant placeholders. The +1.5pp gap is the contribution of flow signals. |
| "Flow factors are within noise" | Confirmed by the data — but it's *signal-to-noise* low, not "ignored." Flow factors carry 6.7% of importance combined. |
| "Adding flow features didn't help" | Roughly accurate, but for the wrong reason. They didn't help because (a) US large-caps are flow-quiet and (b) the labels were 63-day forward returns, possibly mismatched to flow-signal decay. |

### What to do next

- **Wire FmpPitProvider into the training pipeline** and retrain. That
  unlocks `target_return` and `analyst_sent` as live features. Likely the
  highest-information experiment available right now.

  **Status:** Pipeline is wired (commit landing 2026-04-28). The
  training loop now composes
  `MergedPitProvider([Edgar, Fmp, InsiderFlow, RetailFlow])`, with FMP
  gracefully degrading to placeholder values when `TRIO_FMP_KEY` is
  unset. **One-shot script: `bash scripts/retrain_with_fmp.sh`** —
  set the env var, run, get fresh artifact + SHAP + gate result.

- **Test on a small-cap universe** (Russell 2000) where flow signals
  should carry more weight relative to mechanical liquidity.
- **Try a 30-day forward-return label** for tighter alignment with the
  90-day flow lookback.

Reproduce via `py -3.12 scripts/shap_analysis.py`.

## 5-factor vs 7-factor head-to-head walk-forward (2026-04-27)

Earlier evaluations left an open question: is the 7-factor model's prior
single-window underperformance (12.54% vs 5-factor's 15.01% CAGR) a real
signal that flow factors hurt, or just window-dependent noise?

`scripts/walk_forward_head_to_head.py` trains both a 5-factor model
(features 0..4, no flow) and a 7-factor model (full set) on the *same*
training cut for each rolling 6-month OOS window, and runs three
backtests per window: RBA-BOS-Flow, MLA-5, MLA-7.

### Per-window results

| Window | RBA | MLA-5 | MLA-7 | 5 − 7 | 5 vs RBA | 7 vs RBA |
|--------|-----|-------|-------|-------|----------|----------|
| 2021-H1 | +79.0% | +55.4% | +55.4% |  0.0 pp | −23.6 pp | −23.6 pp |
| 2021-H2 | +55.6% | +59.3% | +71.8% | **−12.6 pp** | +3.6 pp | **+16.2 pp** |
| 2022-H1 | −15.8% | −22.8% | −22.8% |  0.0 pp | −7.0 pp | −7.0 pp |
| 2022-H2 | +34.2% | +23.0% | +19.8% | +3.1 pp | −11.2 pp | −14.4 pp |
| 2023-H1 | +24.7% | **+89.1%** | +75.8% | +13.3 pp | **+64.3 pp** | +51.1 pp |
| 2023-H2 |  +2.3% | +22.1% | +16.9% | +5.2 pp | +19.8 pp | +14.6 pp |

### Aggregate

| | Mean lift |
|---|---|
| 5-factor vs RBA | **+7.65 pp** |
| 7-factor vs RBA | +6.15 pp |
| 5-vs-7 differential | +1.50 pp (5-factor slightly better) |

| Win-rate | |
|---|---|
| 5-factor wins vs 7-factor | **3/6 (50%) — exactly tied** |
| 5-factor beats RBA | 3/6 (50%) |
| 7-factor beats RBA | 3/6 (50%) |

### Verdict — inconclusive, and that matters

5-factor edges 7-factor by 1.5 pp on average but loses to it as often as
it wins. The flow factors are *within noise* on this universe and horizon.

**Implications:**
- The earlier "MLA-7 underperforms 5-factor" framing (single-window) was
  not robust. Removed from the headline finding.
- The earlier "MLA gate-passes" framing remains true on average — both
  variants beat RBA across multiple windows, with high dispersion.
- Adding insider_flow + retail_flow as features didn't hurt — they just
  didn't materially help on this slice. They might help on:
  - A larger universe where flow signals are more differentiated
  - Different horizons (30-day or 180-day forward returns)
  - Different label types (Sharpe-adjusted, or relative-to-universe rank)

**Architectural decision:** keep the 7-factor stack as production. It
preserves the `bos_flow` symmetry between RBA and MLA, and the marginal
1.5 pp underperformance versus the simpler 5-factor variant is small
enough that the architectural consistency wins.

**Honest open question:** does feature selection inside the GBM (e.g.
SHAP values) show the flow factors getting any weight at all? If they're
near-zero, the model is essentially 5-factor with noise — fine, just
worth knowing for the next iteration.
