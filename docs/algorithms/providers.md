# SOP — Live Data Providers

**Source of truth:** `packages/data_providers/trio_data_providers/`
**Endpoint:** `POST /universe/{provider_name}?model={bos|mos|four_factor}`

## Architecture invariant

`/score` stays universe-blind. Providers fill canonical fields → client POSTs the rows back to `/score`. This is what lets RBA and (future) MLA share one endpoint without a separate live-data path per engine.

## Providers

| Name | Universe | Coverage (BOS) | Status | Notes |
|------|----------|----------------|--------|-------|
| `yfinance` | S&P 500 / US | All 5 factors. Computes Altman-Z from balance sheet when available. | Active | Free; rate-limited by Yahoo. Heavy import. |
| `tradingview` | US + Malaysia (auto by ticker prefix) | 4 of 5 BOS factors via the screener `scan` endpoint (vol, target_return, dvd_yld, analyst_sent). **No Altman-Z** — TradingView removed `ALT.Z` from the public schema (combine with yfinance/CSV to fill). Partial MOS / 4F coverage where TradingView exposes the column. | Active — **unofficial** | No documented public API; uses `scanner.tradingview.com/{market}/scan` (same endpoint TradingView's web Screener calls). Every response carries an inline warning. ToS may restrict heavy programmatic use. Sentiment normalised from `Recommend.All ∈ [-1, +1]` (clamped) to BOS 1..5 via `1 + (r+1)·2`. |
| `i3investor` | KLCI / Bursa | `target_return` + `analyst_sent` only (price-target page). Also returns `px_last`, `best_target_price`. | Active — partial | 5-second politeness sleep. Set `TRIO_I3_RATE_LIMIT=0` in tests. Resurrected from `notebooks/i3investor_scraper.ipynb`. |
| `bloomberg` | Any | Full BOS / MOS / 4F. | **Stub** | Requires `TRIO_BLOOMBERG_HOST` + `TRIO_BLOOMBERG_PORT` and a working `blpapi` session. Activation steps inline in the file. |

## Sentiment scale alignment

Providers deliver sentiment on different conventions:

| Source | Bullish encoding | Convert to BOS scale (high = bullish) |
|--------|-----------------|---------------------------------------|
| yfinance `recommendationMean` | 1.0 strong buy → 5.0 strong sell | `6 − recommendationMean` |
| TradingView `Recommend.All` | −1.0 strong sell → +1.0 strong buy (clamped) | `1 + (r + 1) · 2`  (so +1 → 5, 0 → 3, −1 → 1) |
| i3investor analyst counts | (sell, hold, buy) | `1 + 4 · buy / (buy+hold+sell)` |
| Bloomberg `EQY_REC_CONS` | 1 sell → 5 buy | identity |

The scoring engine never sees the source convention — providers normalize before `analyst_sent` reaches `/score`.

## Coverage gaps and policy

When a provider can't supply a factor, the row's value is `None` and the scoring engine flags it (`factors[i].flags = ["missing"]`). We never silent-fill with 0 (legacy `bos.py` did this and it skewed quartiles).

For KLCI in particular: `i3investor` covers ~2 of 5 BOS factors. Realistic flow:
1. Pull i3investor for target price + sentiment.
2. Combine with a CSV of fundamentals (volume, dividend yield, Altman-Z) for full coverage.

Or just use Bloomberg once the stub is wired up.

## Adding a new provider

1. Subclass `DataProvider`, implement `coverage()` and `fetch()`.
2. Register in `registry.py`.
3. Add a mocked test in `apps/api/tests/test_providers.py` — never hit real network in tests.
4. Update this SOP.
