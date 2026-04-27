# SOP — QV (Quality-Value) 6-Factor Screen

**Source of truth:** `packages/algorithms/trio_algorithms/rba/qv.py`
**Endpoint:** `POST /score?model=qv`
**Model version:** `rba-qv-1.0.0`

## North star

A composite quality-and-value screen rooted in three landmark factor-investing
strategies. Half the weight is "is this a good business?" (quality) and half
is "is it cheaply priced?" (value). Both questions matter; neither alone is
sufficient.

| Quality side (50%) | Value side (50%) |
|---|---|
| F1 ROE | F4 Earnings Yield |
| F2 Gross Profitability | F5 Book/Market |
| F3 Debt/Equity (reversed) | F6 FCF Yield |

## Theoretical foundations

QV is not invented from scratch — it stands on three published bodies of work:

### 1. Greenblatt's Magic Formula (2006)

*The Little Book that Beats the Market* — Joel Greenblatt's empirical claim
that ranking stocks by combined **earnings yield (EBIT/EV)** + **return on
capital** beats the market over 17 years (1988–2004) by ~10 percentage
points annually.

QV's F4 (`earnings_yield = EBIT / Market_Cap × 100`) is the direct Greenblatt
value signal. Pre-tax to make cross-jurisdiction comparisons cleaner; market
cap rather than enterprise value to keep the data layer simpler (TRIO's
EDGAR layer doesn't yet emit net debt, only total debt).

### 2. Novy-Marx's Gross Profitability (2013)

*"The Other Side of Value: The Gross Profitability Premium"* — Robert
Novy-Marx showed that **gross profit / total assets** is a stronger
predictor of cross-sectional returns than ROE, ROA, or any earnings-based
metric. The intuition: gross profit is harder to manipulate than net
income (no D&A games, no deferred-tax tricks), and total assets is a clean
denominator.

QV's F2 (`gross_profit_to_assets`) is this exact metric.

### 3. Graham/Lynch leverage discipline

Both Benjamin Graham (*The Intelligent Investor*) and Peter Lynch
(*One Up On Wall Street*) treated **debt-to-equity** as a downside hedge:
high-leverage companies look great in good times and explode in bad times.

QV's F3 (`debt_to_equity`) is **reverse-banded** — lower is better. A
company with D/E < 0.5 scores BUY; D/E > 1.5 scores SELL.

## Per-factor specification

### F1 — Return on Equity (ROE %)

```
roe = net_income / shareholders_equity × 100
```

Bands: BUY ≥ 15% · NEUTRAL · SELL < 5%
Default weight: **0.15**

The classic Buffett quality test. ROE > 15% sustained over 5 years is the
"Dean's List" cutoff in Berkshire Hathaway's investment memos.

### F2 — Gross Profitability (Gross Profit / Total Assets)

```
gross_profit_to_assets = (revenue - cogs) / total_assets
```

Bands: BUY ≥ 0.30 · NEUTRAL · SELL < 0.10
Default weight: **0.20** (highest — it's the empirically strongest factor)

Novy-Marx's signature metric. Robust because:
- Gross profit ignores SG&A/D&A noise
- Total assets is verifiable on every balance sheet
- Works across industries (a software company at GP/A=0.7 and a steel mill
  at GP/A=0.15 are both well-positioned in their respective industries)

### F3 — Debt / Equity (REVERSED banding)

```
debt_to_equity = total_debt / shareholders_equity
```

Bands: BUY ≤ 0.5 · NEUTRAL · SELL > 1.5  (lower is better)
Default weight: **0.15**

Graham/Lynch's discipline metric. The reversal is the only one in the
engine — the `_band_reversed` helper handles it explicitly with the same
1/2/3 sub-score scale so it stays comparable.

### F4 — Earnings Yield (EBIT/Market Cap %)

```
earnings_yield = ebit / market_cap × 100
```

Bands: BUY ≥ 8% · NEUTRAL · SELL < 2%
Default weight: **0.20** (highest single value factor)

Greenblatt's Magic Formula value side. ≥8% means the firm earns at least 8
cents pre-tax per dollar of market value — comparable to earning a "yield"
on the stock at acquisition.

Note: pure Greenblatt uses EV (market cap + net debt) to penalize leverage
twice. We use market cap because (a) EBIT/EV requires net-debt extraction,
which the EDGAR provider doesn't currently emit; (b) F3 already penalizes
leverage independently.

### F5 — Book/Market Ratio

```
book_to_market = book_value / market_cap
```

Bands: BUY ≥ 0.6 · NEUTRAL · SELL < 0.2
Default weight: **0.15**

Fama-French (1992) HML factor. Persistent value premium across decades.
The 0.6 / 0.2 thresholds capture roughly the top and bottom decile of
US large-caps in modern markets.

### F6 — Free Cash Flow Yield (FCF/Market Cap %)

```
fcf_yield = (cfo - capex) / market_cap × 100
```

Bands: BUY ≥ 6% · NEUTRAL · SELL < 2%
Default weight: **0.15**

The cash-quality version of earnings yield. Earnings can be massaged
through accruals; cash flow is harder to fake. A high FCF yield + low
earnings yield is a *positive* signal (under-reported earnings); high
earnings yield + low FCF yield is a *negative* signal (accruals quality
issue).

## Scoring & quartiles

Identical to BOS/BOS-Flow:

1. Each factor: raw → band → sub_score (1=SELL, 2=NEUTRAL, 3=BUY).
2. `final_score = Σ (sub_score × weight)` — yields a value in [1.0, 3.0].
3. Quartiles assigned descending by final_score (top 25% = Q1 = BUY-BUY).
4. Recommendation chips map quartile → BUY-BUY / BUY / SELL / SELL-SELL.

Missing factor → flagged with `flags=["missing"]`, sub_score=0; the row
keeps its other factor contributions but scores partial.

## Weight overrides

The `qv_weights` field on `ScoreRequest` accepts a `QvWeights` object with
all six fields. Sum is normalised to 1.0 — UI can pass raw drag-bar values.

Three "named" weight presets that each match a real strategy:

```python
# Pure Greenblatt — earnings yield dominant
QvWeights(f1_roe=0.0, f2_gross_profit_to_assets=0.0, f3_debt_to_equity=0.0,
          f4_earnings_yield=1.0, f5_book_to_market=0.0, f6_fcf_yield=0.0)

# Pure Novy-Marx — gross profitability dominant
QvWeights(f1_roe=0.0, f2_gross_profit_to_assets=1.0, f3_debt_to_equity=0.0,
          f4_earnings_yield=0.0, f5_book_to_market=0.0, f6_fcf_yield=0.0)

# Buffett-style quality-at-reasonable-price
QvWeights(f1_roe=0.30, f2_gross_profit_to_assets=0.20, f3_debt_to_equity=0.15,
          f4_earnings_yield=0.20, f5_book_to_market=0.10, f6_fcf_yield=0.05)
```

Engine emits a warning when overrides differ from canonical so the audit
trail captures the change.

## Required canonical row fields

Single source of truth, mirror in `apps/web/lib/csv.ts`:

| Field | Unit | Source examples |
|---|---|---|
| `roe` | % | Bloomberg `RETURN_COM_EQY`, FMP `returnOnEquity` |
| `gross_profit_to_assets` | ratio | `(revenue - cogs) / total_assets` |
| `debt_to_equity` | ratio | Bloomberg `TOT_DEBT_TO_TOT_EQY`, derived from EDGAR XBRL |
| `earnings_yield` | % | EBIT × 100 / market_cap |
| `book_to_market` | ratio | book_value / market_cap |
| `fcf_yield` | % | (CFO - CapEx) × 100 / market_cap |

EDGAR XBRL today emits:
- ROE: derivable from `NetIncomeLoss` ÷ `StockholdersEquity` (need to add the income tag — currently EDGAR provider only extracts EBIT not net income).
- Gross profit: `Revenues` minus `CostOfRevenue` (need to add CoR tag).
- Debt/Equity: `Liabilities` ÷ `StockholdersEquity` works as a Total Liabilities/Equity proxy; "true" Debt/Equity wants long-term + short-term debt only.
- Earnings yield: `OperatingIncomeLoss` × 100 ÷ market_cap (need price layer at as_of).
- Book/Market: `StockholdersEquity` ÷ market_cap (need price layer).
- FCF yield: `NetCashProvidedByUsedInOperatingActivities` − CapEx (PaymentsToAcquirePropertyPlantAndEquipment), divided by market_cap.

**Status today:** the engine is fully implemented and tested with
hand-crafted row dicts (including via CSV upload). The PIT data layer
extension to emit these new fields from EDGAR is the next data-side
project. Until that lands, QV runs against:
- CSV uploads (Bloomberg-style headers auto-mapped, see `apps/web/lib/csv.ts`)
- Live yfinance fetch for the simpler fields (yfinance.info has many of these)
- Hand-curated test fixtures

## Honest limitations

- **No PIT-history extension yet.** This engine is RBA, not MLA. To use
  it in the existing walk-forward gate, we'd need to extend
  `EdgarPitProvider` to emit ROE, gross profit, FCF, and join market-cap
  data — that's deferred work.
- **Magic Formula uses EBIT/EV, not EBIT/MarketCap.** Our F4 is a
  simplification; F3 catches the leverage penalty independently. For a
  pure-Greenblatt run, paying for the net-debt enrichment is the right
  upgrade.
- **No earnings stability term.** Buffett-style quality includes 5-year
  EPS variance; we'd need multi-year row history to compute it. Out of
  scope for the v1 single-snapshot engine.
- **Banding thresholds are calibrated for US large-caps.** Small-caps
  and emerging-market issuers have different distributions; the
  thresholds would need re-calibration per universe.

## Research / extension queue

1. Extend EDGAR XBRL extraction with `NetIncomeLoss`, `CostOfRevenue`,
   `NetCashProvidedByUsedInOperatingActivities`,
   `PaymentsToAcquirePropertyPlantAndEquipment`. ~2 hours.
2. Add F7 — earnings stability (5y EPS coefficient of variation).
   Requires multi-year row history. ~half-day.
3. Wire QV into the walk-forward gate runner for an apples-to-apples
   comparison vs RBA-BOS-Flow + MLA-v0. ~1 hour once data layer is ready.
4. Universe-specific threshold calibration via empirical
   percentile bands instead of hand-set absolute thresholds.

## References

- Greenblatt, J. (2006). *The Little Book That Beats the Market*. Wiley.
- Novy-Marx, R. (2013). "The Other Side of Value: The Gross Profitability
  Premium." *Journal of Financial Economics*, 108(1), 1–28.
- Fama, E.F. & French, K.R. (1992). "The Cross-Section of Expected Stock
  Returns." *Journal of Finance*, 47(2), 427–465.
- Piotroski, J.D. (2000). "Value Investing: The Use of Historical
  Financial Statement Information to Separate Winners from Losers."
  *Journal of Accounting Research*, 38, 1–41.
- Graham, B. (1949). *The Intelligent Investor*. Harper & Brothers.
