# SOP — Backtester (P4 + walk-forward)

**Source of truth:** `packages/backtester/trio_backtester/`
**Endpoints:**
- `POST /backtest?strategy={sma|rba_snapshot}` — single equity curve.
- `POST /backtest/walk_forward?strategy=...&n_windows=N` — N non-overlapping sub-runs + aggregate.

## North star

Validate strategies against history with metrics a PM trusts: equity curve,
CAGR, Sharpe, max drawdown, total return — vs an equal-weight buy-and-hold
benchmark of the same universe.

## Strategies

### `sma` — SMA crossover (price-only)

Per ticker, hold long when fast-SMA > slow-SMA, flat otherwise. Equal-weight
across active long names; mark-to-market daily; round-trip fees on weight
changes. **No fundamentals → no lookahead bias.** Numbers are honest.

Inputs: `fast` (default 50), `slow` (default 200), `fee_bps` (default 5).

### `rba_snapshot` — top-N by RBA score

At t=0, score the universe with today's BOS/MOS/4F engine via yfinance.
Take the top-N tickers by `final_score`, equal-weight, buy-and-hold with
periodic rebalance back to flat weights.

⚠️ **Lookahead bias.** Today's fundamentals are applied to historical prices.
A stock that became a darling in 2024 still scores "BUY" in our 2015 backtest.
Survivorship bias too — bankrupt tickers don't appear in today's snapshot.
**Demo only.** Engine surfaces this as the first warning on every response.

Inputs: `model` (default `bos`), `top_n` (default 3), `rebalance_days`
(default 21), `fee_bps`.

## Walk-forward

`run_walk_forward(req, strategy, n_windows=N, history=, dates=, score_fn=)`
splits `dates` into N contiguous, near-equal slices (first `n % k` slices get
one extra day; slices with <2 days are dropped) and runs the chosen strategy
on each. Pure function — re-uses `run_backtest` per slice; no new fetches.

Aggregate fields:
- `mean_sharpe` — average of per-window Sharpes
- `median_total_return` — robust to one-window outliers
- `total_return_std` — sample stdev across windows; high = regime-dependent
- `pct_windows_beating_benchmark` — strategy `total_return` > B&H per window
- `pct_windows_positive` — windows with `total_return > 0`

Use this before believing any single equity curve. A strategy with one good
2020-2021 leg and four flat years has a misleading aggregate metric; the
per-window table makes that obvious.

### `rba_pit` — Path 3 point-in-time

Re-scores the universe at every rebalance using fundamentals as-of that
date. No lookahead when paired with a real PIT provider. See
`packages/data_providers/trio_data_providers/pit.py`:

- **MockPitProvider** (active default) — deterministic synthetic time-series.
  Same ticker on the same date always returns the same numbers; smooth
  cross-date drift gives the strategy something to react to. Every result
  carries a `synthetic_pit:` warning. Useful for demoing the architecture
  end-to-end without a paid feed.

- **EdgarPitProvider** — SEC EDGAR Companyfacts adapter, **live**. Pulls
  XBRL filings via `data.sec.gov`, maps tags to Altman-Z components,
  filters by `filed <= as_of` for the no-lookahead invariant, and returns
  one canonical row per ticker. US tickers only (CIK-based lookup).
  Required env: `TRIO_SEC_UA="Mailto contact@example.com"` (SEC rule).
  Cache lives at `~/.trio_cache/edgar/`, 24-hour TTL.

  - `altman_z`: Altman **Z'** (private-firm variant), avoids needing
    as-of market cap. Book-value-of-equity / liabilities replaces the
    market-cap term. Returns None for issuers without current-asset /
    current-liability reporting (e.g. banks).
  - `dvd_yld_ind`: when `prices=` is supplied (the engine does this
    automatically), uses **market** yield = most-recent-10-K DPS / as-of
    forward-filled price. Falls back to book-yield (DPS / BVPS) when no
    price data is available. Tag fallback chain: `CommonStockDividendsPerShareDeclared`
    then `CommonStockDividendsPerShareCashPaid` (J&J etc.); prefers
    whichever populates a more recent `end`. `latest_max_at_end` is used
    instead of `latest_as_of` so we get the full-year sum, not a quarter,
    when XBRL stores both rows under the same end-date.
  - `vol_avg_3m`: when `volumes=` is supplied, computed as the 63-day
    rolling mean of daily volume ending at as_of. Otherwise None.
  - `target_return`, `analyst_sent`: forward-looking analyst data, not in
    XBRL filings — always None unless paired with FmpPitProvider via
    `MergedPitProvider` (see below).

- **FmpPitProvider** — Financial Modeling Prep adapter for the two
  forward-looking factors EDGAR can't supply. Free key required at
  `TRIO_FMP_KEY`; sign up at financialmodelingprep.com (250 req/day).
  - `target_return` = (mean of analyst price targets in trailing 90d
    ending at as_of) ÷ as-of price − 1, ×100.
  - `analyst_sent` = mean of upgrade/downgrade `newGrade` mapped via
    `GRADE_TO_SCORE` to the BOS 1–5 scale, over trailing 90d.
  - Free-tier coverage on `/price-target` and `/upgrades-downgrades` may
    cap historical depth — sparse for `as_of` dates pre-2022. Each row
    carries `_fmp_targets` / `_fmp_ratings` counts so callers see how
    many records actually fed the consensus.

- **MergedPitProvider** — composes multiple PitProviders into one row
  stream, last-non-None-wins. Standard config:
  `MergedPitProvider([EdgarPitProvider(), FmpPitProvider()])` →
  altman_z + dvd_yld_ind + vol_avg_3m from EDGAR/yfinance, target_return
  + analyst_sent from FMP, all PIT-honest, full 5-of-5 BOS coverage.
  Coverage summary appears as the first warning on every result.

  Switch via `TRIO_PIT_PROVIDER` env in the API process:
  - `mock` (default) — synthetic deterministic
  - `edgar` — 3-of-5 PIT factors (US-only)
  - `fmp` — analyst factors only
  - `edgar+fmp` — full 5-of-5 PIT (needs both `TRIO_SEC_UA` and `TRIO_FMP_KEY`)

Inputs same as `rba_snapshot`: `model`, `top_n`, `rebalance_days`, `fee_bps`.
Engine emits a `Rebalances: N; first selection ...` info warning.

## Metrics

All in `metrics.py` — pure functions, no I/O:

- `cagr(values, n_days)` — `(end / start) ^ (252 / n_days) - 1`
- `sharpe(returns)` — annualised by √252; risk-free defaults to 0
- `max_drawdown(values)` — most-negative peak-to-trough fraction
- `total_return(values)` — `end / start - 1`
- `win_rate(trade_returns)` — fraction of trades with positive return

## Data layer

`data.py::fetch_history(tickers, start, end)` calls `yfinance.download` and
returns `(sorted_dates, {ticker: {date: adj_close}})`. Auto-adjusts for splits
& dividends. Tickers yfinance can't resolve are silently dropped.

For tests, `app/main.py::backtest` is wired so `monkeypatch.setattr` on
`app.main.fetch_history` replaces the network call with fixtures.

## Architecture invariant

Engine is pure — `run_backtest(req, strategy, history=, dates=, score_fn=)`
is a deterministic function of its inputs. The FastAPI layer owns:
- Pulling price history (yfinance)
- Building `score_fn` for `rba_snapshot` (yfinance + RBA engine)
- HTTP error mapping

## Adding a new strategy

1. Add `strategies/<name>.py` with a `simulate(...)` returning `(equity, trade_returns)`.
2. Add the literal to `StrategyId` in `contracts.py`.
3. Branch on the name in `engine.run_backtest`.
4. Add to `STRATEGIES` in `apps/web/components/BacktestCard.tsx`.
5. Add tests with deterministic fixtures — never real network.
6. Update this SOP.
