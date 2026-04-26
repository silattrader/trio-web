# SOP — Retail Flow Factor (Wikipedia pageviews)

**Source of truth:** `packages/data_providers/trio_data_providers/retail_pit.py`
**Surfaced as:** the `retail_flow` field on canonical scoring rows.

## North star

Detect "retail attention surges" — when a stock is suddenly in the public
eye well beyond its normal baseline. In a fundamentals-aware framework,
this is a **contrarian signal** (froth detector), not a buy signal. By the
time retail traders have piled in to the search-engine + Wikipedia
pageview tail, the smart-money entry point has typically passed.

## Data source

[Wikimedia Pageviews API](https://wikitech.wikimedia.org/wiki/Analytics/AQS/Pageviews)
— free, no key, no commercial-use restriction. Daily pageview counts per
article, finalised ~24h after the day in question and never revised.
History goes back to 2015-07-01.

Endpoint:
```
https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/
  en.wikipedia/all-access/all-agents/{article}/daily/{start}/{end}
```

Set `TRIO_WIKI_UA` to a contact email per Wikimedia's user-agent policy
(default falls back to a project-identifying string). Cache lives at
`~/.trio_cache/wikipedia/`.

## Scoring logic

1. For each ticker, look up the Wikipedia article slug via
   `TICKER_TO_ARTICLE` (curated dict — extend for your universe).
2. Pull daily pageviews for the trailing 365 days ending at `as_of`.
3. Split into:
   - **Recent**: trailing 30 days
   - **Baseline**: days 31–365
4. Compute z-score: `(recent_mean − baseline_mean) / baseline_std`.
5. Map to 1–5 BOS scale:
   ```
   z >= +2.0  → 1.0  (extreme attention spike — strong contrarian SELL)
   z >= +1.0  → 2.0  (elevated attention — mild SELL)
   z <  +1.0  → 3.0  (normal range — neutral)
   ```

Why no upside scoring? Low pageview counts don't predict positive returns,
and F1 (volume) already penalises illiquidity. Keeping retail_flow purely
a "is the crowd already here?" detector keeps it orthogonal.

## Live smoke test (as-of 2023-06-01)

| Ticker | Score | z-score | Recent | Baseline | Read |
|--------|-------|---------|--------|----------|------|
| AAPL   | 3.0   | -0.22   | 17,092 | 18,650 | normal |
| MSFT   | 3.0   | -0.95   |  9,481 | 13,710 | quiet |
| GME    | 3.0   | -0.46   |  1,468 |  2,096 | post-meme cooldown |
| AMC    | 3.0   | -0.33   |    709 |    916 | likewise |
| TSLA   | 3.0   | -0.11   | 10,270 | 10,661 | steady-state |
| **NVDA** | **1.0** | **+5.85** | **8,657** | **3,195** | **AI-hype apex (Computex keynote)** |
| JNJ    | 3.0   | -0.08   |  1,904 |  2,012 | sleeper |
| PLTR   | 2.0   | +1.24   |  2,587 |  1,897 | early AI-software pump |

NVDA's z-score of +5.85 is genuinely off-the-charts. Note: this triggered
a contrarian SELL signal that was *wrong* short-term — NVDA continued to
rip higher through 2023 and into 2024. **The factor is a froth detector,
not a market-timing oracle.** Use as one input among many.

## Honest caveats

- **English Wikipedia only.** International tickers (Asia/Europe-only listings)
  get nothing. A fix would consume multiple language editions and pool —
  documented as future work.
- **Article-slug mapping is hand-curated.** ~50 tickers covered; extend
  `TICKER_TO_ARTICLE` for your universe. A yfinance-driven auto-resolver
  would work but is rate-limited.
- **Pageviews ≠ buying interest.** A spike could be PR/news/scandal, not
  trading attention. False positives expected.
- **Contrarian-default may not suit momentum strategies.** If you're
  building a momentum overlay, invert the scoring. The provider exposes
  the raw `_retail_attention_z` field for custom downstream logic.
- **Wikimedia rate-limits anonymous traffic.** Set `TRIO_WIKI_UA` and
  cache aggressively. The 7-day TTL is intentional — pageviews are final.

## Switching the provider on

`TRIO_PIT_PROVIDER=all` activates the full stack: EDGAR + FMP + insider + retail.

Other combos:
```
TRIO_PIT_PROVIDER=retail              # retail flow only (debugging)
TRIO_PIT_PROVIDER=edgar+fmp+insider   # 5-of-5 BOS + insider, no retail
```

## Wire into BOS-Flow

`retail_flow` is a new canonical field on the row dict. The existing BOS
engines don't read it yet — that's the next step (a `bos_flow` variant
that combines BOS + insider_flow + retail_flow into a 7-factor score).
For now the field is captured and surfaced; the scoring weights happen
when `bos_flow.py` is written.
