# TRIO Web

Equity decision-support platform reviving [shah05/trio-mvp](https://github.com/shah05/trio-mvp) and [shah05/trio-app](https://github.com/shah05/trio-app). Rule-based scoring (RBA) today, machine-learning scoring (MLA) on the same contract later.

> Decision-support only. Not investment advice.

## Status — P4 (backtester)

✅ Algorithm package (`trio_algorithms`): BOS, MOS, 4-Factor — pure functions, Pydantic-validated.
✅ Data providers (`trio_data_providers`): yfinance (active, S&P 500), TradingView (active, US+MY unofficial scanner), i3investor (active, KLCI partial), Bloomberg (stub, credentials gated).
✅ Backtester (`trio_backtester`): SMA crossover (price-only, no lookahead) + RBA-snapshot (lookahead-flagged, demo only).
✅ FastAPI service (`apps/api`): `POST /score`, `POST /universe/{provider}`, `POST /backtest`, `GET /providers`.
✅ Next.js 15 + Tailwind UI (`apps/web`): CSV upload, live-tickers fetch, hosted backtester with equity-curve chart vs benchmark.
✅ 49 tests covering quartile assignment, provider mocking, SMA/RBA-snapshot strategies, metric maths, endpoint round-trips.
⏳ Path 3 (point-in-time fundamentals), P5–P6 MLA — see [docs/GOAL.md](docs/GOAL.md).

## Layout

```
apps/api/                   # FastAPI service — /score, /universe, /backtest, /providers
apps/web/                   # Next.js 15 + Tailwind UI
packages/algorithms/        # trio_algorithms — RBA engines + shared contracts
packages/data_providers/    # yfinance · tradingview · i3investor · Bloomberg (stub)
packages/backtester/        # trio_backtester — SMA + RBA-snapshot strategies
docs/
  GOAL.md                   # North Star + 6-phase roadmap
  PRD.md                    # Product requirements
  algorithms/               # SOPs — update before changing engine code
                            #   bos.md · mos.md · four_factor.md · providers.md · backtester.md
infra/                      # docker-compose — P3+
```

## Quick start

```bash
# 1. Install Python side (editable, all three packages)
python -m venv .venv && source .venv/Scripts/activate    # Windows: .venv\Scripts\activate
pip install -e packages/algorithms
pip install -e packages/data_providers
pip install -e packages/backtester
pip install -e "apps/api[dev]"

# 2. Run tests
cd apps/api && pytest -q

# 3. Boot the API (terminal 1)
uvicorn app.main:app --reload --port 8001
# -> http://localhost:8001/docs for the interactive Swagger UI

# 4. Boot the web UI (terminal 2)
cd apps/web
npm install
npm run dev
# -> http://localhost:3000   (Next.js proxies /api/* to the FastAPI service)
```

The home page accepts a CSV upload (Bloomberg-style headers auto-mapped) or a one-click sample
KLCI universe. Click any row to drill into the per-factor breakdown and radar chart.

## Sample request

```bash
curl -X POST 'http://localhost:8001/score?model=bos' \
  -H 'content-type: application/json' \
  -d '{
    "universe": "KLCI",
    "rows": [
      {"ticker":"MAYBANK MK","vol_avg_3m":2000000,"target_return":18,"dvd_yld_ind":6.4,"altman_z":3.1,"analyst_sent":4.4}
    ]
  }'
```

## Design invariants

- **One contract.** RBA and MLA both return `ScoreResponse`. The web UI never branches on engine type.
- **Logic-first.** Update `docs/algorithms/<model>.md` before editing the engine code.
- **No silent NaN-filling.** Missing factor → flagged, not zeroed (legacy `bos.py` zero-filled and skewed quartiles).
- **Universe-relative.** Scores are valid only inside the request's universe; cross-run comparisons are unsupported.
- **MLA gate.** ML model cannot ship to users until backtested net-of-fees return ≥ RBA on the same universe + period.
