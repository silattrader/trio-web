# SOP — Curated Universes

**Source of truth:** `packages/data_providers/trio_data_providers/universes.py`
**Endpoint:** `GET /universes`

## Three universes today

| ID | Label | Snapshot | Coverage | Size |
|---|---|---|---|---|
| `curated_demo` | Curated demo (28 US large caps) | 2026-04-26 | US | 28 |
| `sp500_top_100` | S&P 500 — top 100 by market cap | 2024-02-01 | US | ~100 |
| `klci_30` | FBM KLCI 30 (limited PIT coverage) | 2026-04-01 | MY | 30 |

`coverage` is "us" or "my" and determines which provider stack delivers
which factors. **The two coverage zones are not symmetric.** US tickers
get the full 7-of-7 PIT pipeline; KLCI tickers get only the price-derived
factors today. This document spells out exactly what.

## Per-factor coverage by region

| Factor | US (EDGAR + FMP + Wiki + Form 4) | MY (Bursa + i3investor) |
|---|---|---|
| F1 `vol_avg_3m` | yfinance ✓ | yfinance for KLCI tickers ✓ |
| F2 `target_return` | FMP `/price-target` ✓ | i3investor (partial) ⚠ |
| F3 `dvd_yld_ind` | EDGAR (book-yield) or yfinance (market) ✓ | i3investor (partial) ⚠ |
| F4 `altman_z` | EDGAR XBRL (Z′) ✓ | None today ✗ |
| F5 `analyst_sent` | FMP `/upgrades-downgrades` ✓ | None today ✗ |
| F6 `insider_flow` | SEC Form 4 ✓ | None today (Bursa announcements would need a scraper) ✗ |
| F7 `retail_flow` | English Wikipedia ✓ | English Wikipedia (~17 of 30 mapped) ⚠ |

So a KLCI run today returns:
- Full F1 (volume from yfinance)
- Partial F2/F3 if i3investor responds (the provider has its own gaps)
- F7 for ~half the names where an English Wikipedia article exists
- Nothing for F4/F5/F6

That's roughly 1.5–2 factors of 7. **The MLA model trained on the 28-name
US basket should not be expected to generalize to KLCI** — different
fundamental distributions, missing factor inputs at inference, different
analyst-coverage regimes.

## What works today

- **CSV upload** of any KLCI universe with Bloomberg-style fundamentals
  (the original use case the engine was built for) — covers all 5 BOS
  factors via the spreadsheet, no PIT bias, works offline.
- **Live yfinance** scoring of KLCI tickers (BOS gets vol + altman_z if
  the i3investor provider responds; the other factors are best-effort).
- **Read-only browsing** of the universe lists via the curated
  buttons in the UI.

## What doesn't work today (deferred)

Real PIT scoring of KLCI requires:

1. **Bursa Malaysia announcements scraper** for insider transactions
   (no SEC analogue) — multi-day project. Bursa publishes them as PDFs;
   parsing reliably is its own thing.
2. **A Malaysian fundamentals feed** to compute Altman Z′ point-in-time —
   options: IBES via Refinitiv (paid), EquitiesTracker (paid), Bloomberg
   (gated), or scraping i3investor financial pages (fragile).
3. **Bahasa Wikipedia coverage** for retail attention — the `_wikipedia_client`
   currently hard-codes `en.wikipedia` in the URL. Adding `ms.wikipedia`
   is ~5 lines but the article-slug mapping for ~30 KLCI names needs
   manual curation.

These are documented as "later" rather than "broken". The current state
is honest: SP500 demo is feature-complete, KLCI demo is BOS-CSV / live-prices
only and clearly labelled as such in the UI.

## Refresh cadence

Lists are hand-curated. Plan to refresh annually:

- **SP500 top 100:** verify against
  https://en.wikipedia.org/wiki/List_of_S%26P_500_companies — pick top 100
  by `MARKET CAPITALIZATION`. Update `snapshot` field.
- **KLCI 30:** verify against
  https://www.bursamalaysia.com/market_information/equities_prices?b=AC —
  the 30 components rotate via the Bursa Index Review committee, twice
  a year.
- **Curated demo:** keep static. It's the universe the existing MLA gate
  results were validated on; changing it invalidates documented
  performance numbers in `docs/algorithms/mla.md`.

## Adding a new universe

1. Append a `Universe(...)` instance to `universes.py` and register in `ALL`.
2. Add Wikipedia article slugs for the new tickers to `TICKER_TO_ARTICLE`
   in `retail_pit.py` so retail_flow works.
3. If the universe is non-US, document the per-factor coverage gap here.
4. Test: `GET /universes` should return the new entry.
