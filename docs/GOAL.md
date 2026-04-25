# TRIO Web — Project Goal

**Owner:** silattrader@gmail.com
**Date:** 2026-04-25
**Status:** Pre-build (docs phase)
**Audience:** Portfolio piece / demo — polish, narrative, and explainability outweigh scale. No public sign-ups, no SLA pressure.
**Ecosystem fit:** TBD. Build standalone at `C:\Users\User\trio-web\` for now; revisit folding into MAS / Aegis Prime once P2 is demoable.
**Scope commitment:** Full roadmap, P0 → P6 (RBA backend through MLA promotion).
**Source DNA:**
- [shah05/trio-mvp](https://github.com/shah05/trio-mvp) — Python rule-based scoring engines (BOS, MOS, 4-factor)
- [shah05/trio-app](https://github.com/shah05/trio-app) — Flutter mobile shell (home / watchlist / recommendation / buy-sell)

---

## 1. North Star

Resurrect TRIO as a **web-based equity decision-support platform** that converts raw fundamentals into transparent, ranked BUY / NEUTRAL / SELL recommendations for the Malaysian (KLCI) and US equity universes — and that can later be upgraded from a **deterministic rule-based algorithm (RBA)** to a **machine-learning algorithm (MLA)** without rewriting the front end.

We are **not** building a black-box robo-advisor. Every recommendation must show the user *why* it scored the way it did (factor-level breakdown). This is the single most important property the system must preserve when MLA replaces RBA.

## 2. Why now

- The original 2019–2020 TRIO POC (Pipfile + Jupyter notebooks + standalone `bos.py` / `mos.py` / `main.py`) proved the scoring logic works on Bloomberg exports, but never shipped a live UX.
- The Flutter `trio-app` repo never wired up to a real backend.
- A web app removes the App Store friction, lets retail investors bookmark a watchlist, and gives us a clean surface to A/B test RBA vs. MLA recommendations side-by-side.

## 3. Phased objectives

| Phase | Name                  | Scope                                                                                                           | Done when…                                                                                            |
|-------|-----------------------|-----------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| P0    | Docs + Scaffolding    | This GOAL.md + PRD.md, repo init, monorepo layout                                                               | Both .md committed; empty `apps/web` + `apps/api` folders exist                                       |
| P1    | RBA backend port      | Re-implement `bos.py`, `mos.py`, and 4-factor model as a FastAPI service with a clean `/score` endpoint         | A CSV upload returns the same quartile ranking as the legacy notebooks (regression test)             |
| P2    | Web UI v1             | Next.js dashboard: upload data → ranked watchlist → drill-down to per-stock factor breakdown                    | A user can upload `bos_*.csv`, see the BUY-BUY / BUY / SELL / SELL-SELL quartiles, click into a stock |
| P3    | Live data adapter     | Replace CSV upload with a pluggable data provider (yfinance free tier first, Bloomberg/Refinitiv later)         | Daily cron refreshes the KLCI universe automatically                                                  |
| P4    | Backtester            | Port the `*_backtester.ipynb` notebooks into a hosted backtest UI                                               | User can pick a date range + universe and see equity curve + Sharpe                                   |
| P5    | MLA shadow mode       | Train a supervised model (gradient boosting first, then LSTM/transformer if data supports) on the same features | MLA predictions log alongside RBA output; no UI change yet                                            |
| P6    | MLA promotion         | Expose MLA recommendations behind a feature flag with side-by-side RBA comparison                               | User can toggle "Rule-based" vs "ML" view; explainability (SHAP) shown per stock                      |

## 4. Non-goals

- **Order execution.** TRIO Web is decision-support only. No broker integration, no live trading, no paper-trading simulator in v1.
- **Portfolio optimization.** Markowitz / Black-Litterman / risk-parity allocation is out of scope; we rank single names, not portfolios.
- **Mobile native.** The Flutter `trio-app` is archived; we will ship responsive web only.
- **Crypto / FX / derivatives.** Equity universes only.

## 5. Success metrics

| Metric                           | P2 target           | P6 target                         |
|----------------------------------|---------------------|-----------------------------------|
| Universes supported              | KLCI + S&P 500 + CSV| KLCI + S&P 500 + CSV (+ regional) |
| Avg time from upload → ranking   | < 5 s for 1k stocks | < 2 s                             |
| Backtested annualized return    | n/a (no backtester) | RBA ≥ KLCI index; MLA ≥ RBA       |
| Explainability coverage          | 100 % factor-level  | 100 % factor-level + SHAP for MLA |
| Hallucination rate (LLM-narrated)| n/a                 | 0 — every claim cites a factor    |

## 6. Guiding principles (carried from MAS / Aegis Prime)

1. **Logic-first.** Update SOPs / `algorithms/*.md` before touching code.
2. **Schema-first.** Every score output must validate against a Pydantic / JSON Schema contract.
3. **Grounded only.** No LLM narrative ships unless every claim maps to a numeric factor or source row.
4. **Reversible model swap.** RBA and MLA must be interchangeable behind the same `/score` contract.
5. **Audit trail.** Every recommendation persisted with input snapshot, model version, and timestamp.
