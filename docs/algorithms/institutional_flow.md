# SOP — Institutional Flow Factor (Form 4 + 13F)

**Source of truth:** `packages/data_providers/trio_data_providers/insider_pit.py`
**Endpoint:** Composes via `MergedPitProvider`; surfaced as the `insider_flow`
field on canonical scoring rows.

## North star

Capture the directional pressure of *informed* market participants. Insiders
(officers, directors, 10%+ owners) and large institutions (hedge funds,
mutual funds, pensions) collectively know more about a security than the
median retail trader. Their net buying/selling is a real, free, PIT-honest
signal — albeit a noisy one.

## What's wired today

### Form 4 — insider transactions

`InsiderFlowPitProvider`. For each ticker × `as_of`:

1. Look up CIK via the cached `company_tickers.json`.
2. Pull the issuer's recent-filings list from `data.sec.gov/submissions/CIK*.json`.
3. Filter to `form == "4"` AND `filingDate <= as_of` AND `filingDate >
   as_of − lookback_days` (default 90).
4. For each filing in the window, fetch the raw XML (cached per-accession
   forever), parse non-derivative transactions.
5. **Filter to discretionary trades only**: `transactionCode ∈ {P, S}`.
   Drops RSU vests (M), grants (A), gifts (G), tax-withholding sales (F),
   and options exercises that aren't directional bets.
6. Aggregate signed dollar value: net = Σ(buys × price) − Σ(sells × price).
7. Normalise by 63-day mean daily dollar volume (price × volume).
8. Score on 1–5 BOS scale (see `score_from_normalised_flow`).

Threshold calibration is **empirical** for mega-caps: insider activity for
$1T+ companies typically lands within ±0.01 of daily $-volume even when
absolute dollar amounts are ~$50M+. Small/mid-caps see much bigger ratios.
Defaults are tuned for the demo's large-cap universe; expect different
optima for small-caps.

### Switch in via env var

```
TRIO_PIT_PROVIDER=edgar+fmp+insider   # full 5-of-5 BOS + insider_flow
TRIO_PIT_PROVIDER=edgar+insider       # just EDGAR + insider, no analyst data
TRIO_PIT_PROVIDER=insider             # insider only (debugging)
```

The insider provider re-uses the EDGAR CIK map (passed via constructor) so
there's no double-fetch.

## What's deferred

### 13F-HR — institutional positions (NOT YET WIRED)

**The signal:** every fund > $100M in AUM must file a 13F-HR within 45 days
of each calendar quarter-end, listing all reportable holdings. Aggregating
across thousands of funds gives "what % of float is held by institutions"
and "Δ institutional ownership QoQ" — a stronger directional signal than
insider activity for liquid large caps.

**Why it's deferred:**

- 13F XMLs reference issuer **CUSIP**, not ticker. Need a CUSIP→ticker map.
  The cleanest free source is the SEC's own quarterly bulk 13F dataset:
  https://www.sec.gov/dera/data/form-13f-data-sets — each quarter is a
  ZIP of TSV files (~50–200 MB), already aggregated, parsable in pandas.
- One quarter's data per ticker is straightforward; building a multi-year
  PIT history requires ingesting ~30 quarterly bulk files.
- This is a multi-hour project of its own. Punted in favour of higher-
  leverage work (MLA promotion gate, retail flow factor).

**Wire-up plan when this is picked up:**

1. New module `_thirteen_f.py`:
   - `download_13f_quarter(year, quarter, dest_dir)` — pulls the SEC's
     bulk ZIP, extracts the relevant TSV (`INFOTABLE.tsv`), caches.
   - `aggregate_holdings(year, quarter)` — group by CUSIP, sum
     `value` and `sshPrnamt`, return a DataFrame.
   - `cusip_to_ticker_map()` — reuse SEC's company_tickers.json + a
     CUSIP enrichment from the 13F filings themselves.
2. `Institutional13FProvider(PitProvider)`:
   - `_quarter_for(date)` returns the most recent fully-reported quarter
     ≤ `as_of − 45 days` (45-day filing lag).
   - For each ticker: lookup CUSIP, fetch aggregated holdings for the
     active quarter and the prior quarter, compute Δ.
   - Emit `inst_ownership_pct` (% of float) and `inst_ownership_delta`
     (QoQ change) on the canonical row.
3. Score: similar 1–5 banding on `delta` — strong institutional accumulation
   = 5; strong distribution = 1.

**Alternative free-but-fragile sources** (ranked):
- WhaleWisdom — has a free tier but rate-limited; HTML scrape risk.
- Stockanalysis.com — clean tables, scrape-friendly.
- HoldingsChannel — RSS feeds of major-fund changes.

For a credible production version, the SEC bulk dataset is the right call.

## Honest caveats

- **Insiders sell more than they buy.** Most insider sales are pre-planned
  10b5-1 transactions, RSU diversification, or estate/gift activity rather
  than directional bets. The `code ∈ {P, S}` filter helps but doesn't
  eliminate noise — many "S" transactions are still scheduled.
- **Only open-market purchases (`P`) carry strong signal.** Insider buys
  happen rarely and almost always indicate the insider believes the stock
  is undervalued. A clean "insider buying" sub-signal would be: count of
  P-code transactions × dollar value, no sells netted.
- **Small-cap calibration differs.** The threshold defaults work for the
  curated 28-stock large-cap universe. Expect re-tuning when broadening to
  Russell 2000.
- **No CIK match → score=None.** Non-US tickers and ADRs without primary
  US filings get nothing. The MergedPitProvider preserves None and the
  scoring engine treats it as a missing factor.
