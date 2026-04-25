# SOP — 4-Factor Legacy Model

**Source of truth:** `packages/algorithms/trio_algorithms/rba/four_factor.py`
**Ported from:** [trio-mvp/app/main.py](https://github.com/shah05/trio-mvp/blob/master/app/main.py)
**Model version:** `rba-four-factor-1.0.0`

## 1. Purpose
The original TRIO 2019 formulation. Kept as a "classic" mode so users can compare BOS against the simpler model.

## 2. Factors
| F  | Field                                | Rule                                                                                              |
|----|--------------------------------------|---------------------------------------------------------------------------------------------------|
| F1 | `ALTMAN_Z_SCORE`                     | > 2 → 1.0 (BUY) · 1–2 → 0.25 (NEUTRAL) · < 1 → 0.0 (SELL)                                         |
| F2 | `EQY_DVD_YLD_EST`                    | > universe mean → 1.0 (BUY) · < mean → 0.5 (SELL)                                                 |
| F3 | `3YR_AVG_RETURN_ON_EQUITY`           | Universe quartiles: > Q75 → 1.0 · Q50–Q75 → 0.75 · Q25–Q50 → 0.5 · < Q25 → 0.0                    |
| F4 | `PE_RATIO` vs `FIVE_YR_AVG_PRICE_EARNINGS` | current < 5yr-avg → 1.0 (BUY) · current > 5yr-avg → 0.0 (SELL)                                |

## 3. Final score
**Note bug-for-bug fidelity:** legacy `main.py` computed
`TOTAL_SCORE = F1 + F2 + F4` — F3 is calculated but excluded from the sum.

We preserve this in `four_factor_legacy()` for reproducibility, and expose `four_factor_corrected()` that includes all four factors (`F1 + F2 + F3 + F4`). Default endpoint uses the corrected version; `?legacy=true` surfaces the original.

## 4. Quartile partition
Same convention as BOS — descending sort on `total_score`, top quartile → `BUY-BUY`.

## 5. Changes from legacy
- F3 inclusion is now correct by default; legacy behaviour preserved behind a flag.
- All thresholds relative to the universe in the request, not historical averages.
