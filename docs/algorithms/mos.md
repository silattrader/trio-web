# SOP — MOS (Margin-of-Safety) Graham Liquid-Value Model

**Source of truth:** `packages/algorithms/trio_algorithms/rba/mos.py`
**Ported from:** [trio-mvp/app/mos.py](https://github.com/shah05/trio-mvp/blob/master/app/mos.py)
**Model version:** `rba-mos-1.0.0`

## 1. Purpose
Estimate a Graham-style liquid value per share, compare to market price and analyst target, and rank by a "Magic Number" that prefers stocks priced near or below liquid value with high analyst upside.

## 2. Inputs
| Field                    | Bloomberg name              | Type  |
|--------------------------|-----------------------------|-------|
| `cash_near_cash`         | `BS_CASH_NEAR_CASH_ITEM`    | float |
| `accounts_receivable`    | `BS_ACCT_NOTE_RCV`          | float |
| `inventories`            | `BS_INVENTORIES`            | float |
| `other_current_assets`   | `BS_OTHER_CUR_ASSET`        | float |
| `accounts_payable`       | `BS_ACCT_PAYABLE`           | float |
| `other_st_liab`          | `BS_OTHER_ST_LIAB`          | float |
| `st_borrow`              | `BS_ST_BORROW`              | float |
| `non_current_liab`       | `NON_CUR_LIAB`              | float |
| `shares_out`             | `EQY_SH_OUT`                | float |
| `px_last`                | `PX_LAST`                   | float |
| `best_target_price`      | `BEST_TARGET_PRICE`         | float |

## 3. Formulas
```
liquid_value         = cash + 0.75·receivables + 0.75·inventory + other_ca
                       − (payables + other_st_liab + st_borrow + non_current_liab)
liquid_value_per_sh  = liquid_value / shares_out
a_premium_pct        = 1 − (liquid_value_per_sh / px_last)
b_target_upside_pct  = (best_target_price − px_last) / px_last
magic_no             = a_premium_pct / b_target_upside_pct        # lower = better
```

Receivables and inventory are haircut to 75 % per Graham's net-net heuristic (cash full weight; inventory depreciates fast).

## 4. Quartile partition
Sort **ascending** on `magic_no` (lower = more attractive):
- Q1 (lowest magic_no) → `BUY-BUY`
- Q4 (highest) → `SELL-SELL`

## 5. Edge cases
- `b_target_upside_pct ≤ 0` (analyst target ≤ current price) → magic_no undefined; row flagged `no_upside`, excluded from quartile ranking.
- `shares_out = 0` or NaN → row flagged `bad_shares_out`, excluded.
- Negative `liquid_value` → still ranked; signals balance-sheet weakness.

## 6. Changes from legacy `mos.py`
- Per §5, divide-by-zero and missing data no longer silently produce inf/NaN that pollute the quartile cuts.
- Pure function; no CSV I/O.
