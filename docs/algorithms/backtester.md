# SOP — Backtester (P4)

**Source of truth:** `packages/backtester/trio_backtester/`
**Endpoint:** `POST /backtest?strategy={sma|rba_snapshot}`

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

### Path 3 — point-in-time fundamentals (deferred)

Requires a paid feed (Sharadar, EOD, SimFin) or SEC EDGAR reconstruction.
Not in P4 scope; plan to revisit before MLA promotion gate (P5+).

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
