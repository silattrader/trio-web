# SOP — BOS (Buy-Or-Sell) 5-Factor Weighted Score

**Source of truth:** `packages/algorithms/trio_algorithms/rba/bos.py`
**Ported from:** [trio-mvp/app/bos.py](https://github.com/shah05/trio-mvp/blob/master/app/bos.py)
**Model version:** `rba-bos-1.0.0`

## 1. Purpose
Rank an equity universe on five fundamental + sentiment factors and partition into BUY/SELL quartiles. Each stock receives a transparent factor-by-factor breakdown.

## 2. Inputs (per stock row)
| Field             | Bloomberg name        | Type  | Required |
|-------------------|-----------------------|-------|----------|
| `vol_avg_3m`      | `VOLUME_AVG_3M`       | float | yes      |
| `target_return`   | `RETURN` (%)          | float | yes      |
| `dvd_yld_ind`     | `EQY_DVD_YLD_IND`     | float | yes      |
| `altman_z`        | `ALTMAN_Z_SCORE`      | float | yes      |
| `analyst_sent`    | `EQY_REC_CONS`        | float | yes      |

Cleanup: trim whitespace; `#N/A Field Not Applicable`, `#N/A N/A`, `-`, `#VALUE!` → NaN. Reject rows with > 30 % required fields NaN.

## 3. Scoring rules
| Factor | Field            | BUY (3)            | NEUTRAL (2)         | SELL (1)           | Weight |
|--------|------------------|--------------------|---------------------|--------------------|--------|
| F1     | `vol_avg_3m`     | > 440 000          | 300 000–440 000     | < 300 000          | 0.20   |
| F2     | `target_return`  | > 15 %             | −15 % – 15 %        | < −15 %            | 0.20   |
| F3     | `dvd_yld_ind`    | > 6 %              | 3.5 % – 6 %         | < 3.5 %            | 0.20   |
| F4     | `altman_z`       | > 2                | 1.5 – 2             | < 1.5              | 0.30   |
| F5     | `analyst_sent`   | > 4.2              | 3.0 – 4.2           | < 3.0              | 0.10   |

`final_score = 0.2·F1 + 0.2·F2 + 0.2·F3 + 0.3·F4 + 0.1·F5` ∈ [1.0, 3.0]

## 4. Quartile partition
After scoring all rows, compute quartile cutpoints on `final_score` and label:
- Q1 → `BUY-BUY` (top 25 %)
- Q2 → `BUY`
- Q3 → `SELL`
- Q4 → `SELL-SELL` (bottom 25 %)

Quartile is **relative to the universe in the request**, not absolute. Two runs on different universes are not comparable.

## 5. Edge cases
- Rows with NaN in any factor: that factor's sub-score = 0; final score still computed; flagged in `factors[i].flags = ["missing"]`.
- Universe of < 4 rows: skip quartile labelling, return raw `final_score` only.
- Ties on the quartile boundary: assigned to the higher (better) quartile.

## 6. Output contract
See `ScoreResponse` in `packages/algorithms/trio_algorithms/contracts.py`. Each row includes `final_score`, `quartile`, `recommendation`, and a `factors[]` array with raw value, band, sub-score, weight, contribution.

## 7. Changes from legacy `bos.py`
- NaN no longer silently filled with 0; explicit handling per §5.
- Quartile boundary uses ≤ on the upper bound (legacy used <, dropping the max-score row into Q4).
- Pure function: takes a list of dicts → returns a list of dicts. No file I/O.
