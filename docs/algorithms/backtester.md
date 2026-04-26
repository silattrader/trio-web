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
  - `dvd_yld_ind`: most-recent-10-K dividend-per-share ÷ book-value-per-share
    — a **book** yield, not market yield. Biased upward when buybacks
    compress BV (e.g. AAPL). A real market yield needs as-of price data
    from yfinance; deferred.
  - `vol_avg_3m`, `target_return`, `analyst_sent` are NOT in XBRL filings
    and are returned as None — the BOS engine treats them as missing.

  Switch in: set `TRIO_PIT_PROVIDER=edgar` in the API process env. Default
  remains MockPitProvider (synthetic, deterministic).

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
