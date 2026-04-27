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

## Three-engine walk-forward head-to-head (2026-04-28)

`scripts/walk_forward_three_engines.py` runs the same rba_pit strategy
three ways across 6 rolling 6-month OOS windows. Results:

| Window | BOS-Flow | QV | MLA-7 |
|--------|----------|-----|-------|
| 2021-H1 (bull leg)     | **+79.0%** | +35.0% | +55.4% |
| 2021-H2 (peak)         | +55.6% | +61.5% | **+71.8%** |
| 2022-H1 (rate shock)   | −15.8% | **−45.6%** | −22.8% |
| 2022-H2 (capitulation) | +34.2% | **+56.9%** | +19.8% |
| 2023-H1 (bottom-bounce)| +24.7% | +49.0% | **+75.8%** |
| 2023-H2 (AI rally)     |  +2.3% |  +4.7% | **+16.9%** |

**Aggregate (mean CAGR across windows):**
- BOS-Flow: +30.0%
- **QV: +26.9%**
- MLA-7: +36.2%

**Head-to-head win rates:**
- QV beats BOS-Flow: **4 of 6 (67%)**
- QV beats MLA-7: 1 of 6 (17%)
- QV best of three: 1 of 6 (17%)

### Honest reading — QV is regime-dependent

The result is consistent with decades of factor-investing literature: **value
strategies have long stretches of underperformance during growth-led regimes,
then dominate during quality-flight periods** (2022-H2 capitulation here).

QV's regime profile across these 6 windows:

- **Strong**: capitulation / mean-reversion (2022-H2: QV +57% vs MLA +20%)
- **Weak**: rate-shock / liquidity contractions (2022-H1: QV −46% vs Flow −16%)
- **Mediocre**: bull legs (2021-H1: QV +35% vs Flow +79%)

The 2022-H1 underperformance (−46% vs Flow's −16%) is particularly telling —
QV's value-tilt got crushed when interest rates spiked and quality-growth
names like AAPL/MSFT held better than cheap-and-cyclical names. This is
expected; the long-run academic case for value rests on cycles where bear
markets eventually rotate back to fundamentals.

### Implications

1. **QV is not a strict replacement for MLA-7.** Across this universe and
   period, MLA-7 is the highest-performing single engine (+36.2 mean CAGR).
   QV's mean lags by ~9 pp; QV beats MLA in only 1 of 6 windows.

2. **QV is complementary.** A 50/50 ensemble of MLA-7 and QV in 2022-H2
   would have averaged +38.4% CAGR — better than MLA alone (+19.8%) and
   approaching QV alone (+56.9%). The decorrelation is the value.

3. **QV's win-rate vs BOS-Flow is strong (67%).** If a user wants to choose
   between rule-based engines, QV is the better default — same governance
   structure, similar simplicity, but a more explicit theoretical
   foundation (Greenblatt + Novy-Marx + Graham vs. BOS's hand-tuned blend).

4. **The 2022-H1 outlier deserves further investigation.** A −46% CAGR
   single-window loss for QV is large enough that the universe selection
   may matter more than the engine — the curated 28-name basket is heavy
   on tech/healthcare and light on energy/materials. A more sector-balanced
   universe might reduce the outlier.

### Reproducible

```
py -3.12 scripts/walk_forward_three_engines.py
```

Output goes to stdout; takes ~5–10 min on warm EDGAR + Wikipedia caches.
First run ~30 min if caches are cold.

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
