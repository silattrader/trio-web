# TRIO Web

> Transparent 7-factor equity scoring with a gate-passed ML model.
> Decision-support for retail traders and institutional fund managers.

[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org)
[![Tests](https://img.shields.io/badge/pytest-128_passing-brightgreen)](#tests)
[![Decision support only — not investment advice](https://img.shields.io/badge/disclaimer-not_investment_advice-amber)](#disclaimer)

**Live demo:** _coming soon — see [docs/DEPLOY.md](docs/DEPLOY.md)_
**Open source:** [github.com/silattrader/trio-web](https://github.com/silattrader/trio-web) (public, MIT)

---

## What this is

A factor-scoring engine that takes a universe of stocks and returns a
ranked watchlist with a per-factor breakdown, an explainable rationale,
and an equity-curve backtest — all under a single stable JSON contract.

Two scoring engines, same contract:

- **RBA** (rule-based) — hand-tuned weighted sum of 7 factors. Transparent.
- **MLA** (machine-learning) — gradient-boosted model trained on real
  point-in-time data. **Promotion-gated**: cannot ship as default until
  backtested return ≥ RBA on the same universe and period.

Both pass the gate today. ([details](docs/algorithms/mla.md))

## Why it's different

- **PIT-honest data.** No lookahead bias. Fundamentals are pulled as-of
  each rebalance date from SEC EDGAR (Altman Z′, dividend yield, dividends).
  Insider activity from Form 4. Retail attention from Wikipedia pageviews.
  Forward-looking analyst data from Financial Modeling Prep.
- **7 factors, all visible.** Volume, target return, dividend yield, Altman
  Z′, analyst sentiment, insider flow, retail flow. Every score has a
  factor-by-factor breakdown panel and a radar chart.
- **Walk-forward verified.** The MLA model was tested across 6 rolling
  out-of-sample windows: it beat RBA in 4 of 6 (mean +11.6 pp CAGR,
  +0.60 Sharpe). The 2 losses are documented openly — that's the
  difference between research and a sales pitch.
- **Bring your own keys.** No signup. Paste your free SEC + FMP + Wiki
  contact emails / API key into the BYOK panel; the site calls third
  parties as you, on your quota. Keys never leave your browser.
- **Open source.** Entire stack — RBA engines, MLA training pipeline,
  walk-forward gate, BYOK plumbing — is here and runs on your laptop.

## Demo gate result (committed, reproducible)

Out-of-sample 2022-2023, model trained 2018-2021, curated 28-name US
large-cap universe:

| Metric        | RBA-BOS-Flow | MLA-7-factor | Lift |
|---------------|--------------|--------------|------|
| Total return  | +9.58% | **+26.36%** | +16.78 pp |
| CAGR          | +4.73% | **+12.54%** | +7.81 pp |
| Sharpe        | 0.33 | **0.62** | +0.29 |
| Max drawdown  | -19.15% | -25.10% | -5.95 pp |

The gate threshold is "CAGR lift ≥ 0 AND Sharpe lift ≥ -0.1." Both pass.
[Reproduce it →](docs/algorithms/mla.md#hard-rule-from-project_constitution)

## Try it

### Hosted demo

_[link will land here once deployed — see [docs/DEPLOY.md](docs/DEPLOY.md)]_

The hosted demo loads with sample data immediately. To pull live point-in-time
data, paste your own free API keys into the **BYOK · demo mode** panel
in the header (instructions in the panel). Free keys at:

- [SEC EDGAR](https://www.sec.gov/about/contact) — just a contact email
- [Wikimedia](https://wikitech.wikimedia.org/wiki/Robot_policy) — just a contact email
- [Financial Modeling Prep](https://site.financialmodelingprep.com/developer/docs/pricing?ref=trio-web) — 250 req/day free tier

### Run locally

```bash
git clone https://github.com/silattrader/trio-web.git
cd trio-web

# 1. Install Python (3.12 recommended — sklearn 1.4+, fastapi)
python -m venv .venv && source .venv/Scripts/activate
make install

# 2. Boot the API (terminal 1)
make run
# -> http://localhost:8001/docs

# 3. Boot the web UI (terminal 2)
cd apps/web && npm install && npm run dev
# -> http://localhost:3000

# 4. (Optional) Set fallback keys
export TRIO_SEC_UA="Mailto you@example.com"
export TRIO_WIKI_UA="Mailto you@example.com"
export TRIO_FMP_KEY="<from financialmodelingprep.com>"
```

## Architecture

```
                      Browser (Next.js · Tailwind · recharts)
                       │
                       │ /api/* + X-TRIO-* headers (BYOK)
                       ▼
                      FastAPI · uvicorn
                       │
            ┌──────────┼──────────┬───────────┬───────────┐
            ▼          ▼          ▼           ▼           ▼
         RBA         MLA       Backtester  PIT data   Walk-forward
        (BOS/        (joblib    (SMA +     providers  (rolling OOS
        BOS-Flow/    GBR)       rba_snap/  (EDGAR /   gate eval)
        MOS/4F)                 rba_pit)    FMP / Wiki/
                                            Form 4)
```

| Package | Responsibility |
|---------|---------------|
| `trio_algorithms` | RBA engines (BOS, BOS-Flow, MOS, 4-Factor) + MLA (gradient-boosted, joblib-persisted) + shared `ScoreResponse` contract + promotion-gate logic |
| `trio_data_providers` | Live data adapters: yfinance (price), EDGAR (XBRL fundamentals), FMP (analyst), Wikipedia (retail attention), Form 4 (insider flow), Mock (synthetic for tests). Composable via `MergedPitProvider` |
| `trio_backtester` | Pure-function backtest engine: SMA crossover, RBA-snapshot (lookahead-flagged), RBA-PIT (point-in-time, no lookahead). Walk-forward harness |
| `apps/api` | FastAPI: `/score`, `/universe`, `/backtest`, `/backtest/walk_forward`, `/byok/status`. Per-request key injection via `contextvars` middleware |
| `apps/web` | Next.js 15 + React 19. Settings panel for BYOK, factor sliders, equity-curve chart, factor radar |

## Documentation

| Doc | Topic |
|-----|-------|
| [docs/GOAL.md](docs/GOAL.md) | North Star + 6-phase roadmap |
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Vercel + Render deployment in 10 minutes |
| [docs/algorithms/bos.md](docs/algorithms/bos.md) | 5-Factor Buy-or-Sell engine |
| [docs/algorithms/mla.md](docs/algorithms/mla.md) | ML model + gate result + walk-forward |
| [docs/algorithms/backtester.md](docs/algorithms/backtester.md) | SMA, RBA-snapshot, RBA-PIT strategies |
| [docs/algorithms/institutional_flow.md](docs/algorithms/institutional_flow.md) | Insider flow + 13F-deferred path |
| [docs/algorithms/retail_flow.md](docs/algorithms/retail_flow.md) | Wikipedia attention z-score |

## Tests

```bash
make test          # 128 pytest, ~5s
cd apps/web && npx tsc --noEmit   # TypeScript check
ruff check packages apps/api      # Python lint
```

## Design invariants

- **One contract.** RBA and MLA both return `ScoreResponse`. The web UI
  never branches on engine type.
- **No silent NaN-filling.** Missing factor → flagged, never zeroed (the
  legacy `bos.py` zero-filled and skewed quartiles).
- **Logic-first.** Every algorithm has an SOP doc that updates *before*
  the code changes.
- **MLA gate.** Cannot ship as default until backtested return ≥ RBA on
  the same universe + period. Today's status: **passed** at +7.81 pp
  CAGR with +0.29 Sharpe lift, validated across 4 of 6 walk-forward
  windows.
- **Universe-relative.** Scores are valid only inside the request's
  universe. Cross-run comparisons are unsupported by design.

## Disclaimer

TRIO Web is research / decision-support tooling, not licensed investment
advice. The output is opinion derived from public-domain factor models
applied to publicly-available data. Use at your own risk.

## Acknowledgements

- Data: [SEC EDGAR](https://www.sec.gov/edgar) · [Financial Modeling Prep](https://site.financialmodelingprep.com/developer/docs?ref=trio-web) · [Wikimedia Pageviews](https://wikitech.wikimedia.org/wiki/Analytics/AQS/Pageviews) · yfinance
- Built on: FastAPI · Next.js · scikit-learn · recharts · pydantic · Tailwind

Some links above are referral / affiliate links — they pay TRIO a small
commission if you sign up; the price you pay is unchanged.
