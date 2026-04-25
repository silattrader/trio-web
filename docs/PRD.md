# TRIO Web — Product Requirements Document (PRD)

**Owner:** silattrader@gmail.com
**Date:** 2026-04-25
**Companion doc:** [GOAL.md](./GOAL.md)
**Source legacy code:** [trio-mvp](https://github.com/shah05/trio-mvp), [trio-app](https://github.com/shah05/trio-app)
**Audience:** Portfolio / demo project. Optimize for explainability and narrative quality, not scale.
**Day-one universes:** KLCI (Bursa Malaysia) · S&P 500 (US) · Universe-agnostic CSV upload.
**Scope commitment:** Full P0 → P6 roadmap (RBA → MLA).

---

## 1. Problem statement

Retail and semi-pro equity investors waste hours each week pulling fundamentals from Bloomberg / i3investor / Yahoo, pasting them into Excel, and applying personal scoring heuristics. The 2019–2020 TRIO POC proved a transparent factor-scoring engine produces a defensible, repeatable BUY/SELL signal — but the engine lived in standalone Python scripts and Jupyter notebooks and never reached an end user. **TRIO Web** turns that engine into a hosted decision-support tool, with a clean upgrade path from rule-based scoring (RBA) to machine-learning scoring (MLA).

## 2. Target users

Primary audience for v1 is **the builder's own portfolio / demo** — recruiters, technical reviewers, and MAS-ecosystem visitors evaluating the project. Personas below describe who the *eventual* tool would serve and inform UX decisions, but no public onboarding work is committed in v1.

| Persona                  | Goal                                                            | Pain today                                                  |
|--------------------------|-----------------------------------------------------------------|-------------------------------------------------------------|
| Retail value investor    | Find undervalued KLCI / US names with strong balance sheets     | Manually computes Altman-Z + P/E + dividend yield in Excel  |
| Junior buy-side analyst  | Filter a 100-name coverage list to a 10-name shortlist          | Has terminal access but no consistent scoring framework     |
| Quant-curious DIY trader | Learn whether a rules engine or ML model would have outperformed | No accessible backtester ties fundamentals to forward returns |
| Technical reviewer       | Evaluate the builder's RBA→MLA design and explainability story  | Most fintech demos are black-box robo-advisors              |

## 3. Core algorithms (ported verbatim from `trio-mvp`)

### 3.1 BOS — "Buy-Or-Sell" 5-factor weighted score

| Factor | Field                  | Buy (3)            | Neutral (2)         | Sell (1)           | Weight |
|--------|------------------------|--------------------|---------------------|--------------------|--------|
| F1     | `VOLUME_AVG_3M`        | > 440 000          | 300 000–440 000     | < 300 000          | 20 %   |
| F2     | `RETURN` (analyst tgt) | > 15 %             | −15 % – 15 %        | < −15 %            | 20 %   |
| F3     | `EQY_DVD_YLD_IND`      | > 6 %              | 3.5 % – 6 %         | < 3.5 %            | 20 %   |
| F4     | `ALTMAN_Z_SCORE`       | > 2                | 1.5 – 2             | < 1.5              | 30 %   |
| F5     | `EQY_REC_CONS`         | > 4.2              | 3 – 4.2             | < 3                | 10 %   |

`FINAL_SCORE = 0.2·F1 + 0.2·F2 + 0.2·F3 + 0.3·F4 + 0.1·F5`
Quartile partition → **Q1 BUY-BUY · Q2 BUY · Q3 SELL · Q4 SELL-SELL**

### 3.2 MOS — Margin-of-Safety (Graham liquid value)

```
LIQUID_VALUE       = CASH + 0.75·RECEIVABLES + 0.75·INVENTORY + OTHER_CA
                     − (PAYABLES + OTHER_ST_LIAB + ST_BORROW + NON_CUR_LIAB)
LIQUID_VALUE_PS    = LIQUID_VALUE / SHARES_OUT
A_PREMIUM_PCT      = 1 − (LIQUID_VALUE_PS / PX_LAST)
B_TARGET_UPSIDE    = (BEST_TARGET_PRICE − PX_LAST) / PX_LAST
MAGIC_NO           = A_PREMIUM_PCT / B_TARGET_UPSIDE       # lower = more attractive
```
Sort ascending on `MAGIC_NO`, partition into quartiles (Q1 = strongest BUY).

### 3.3 4-Factor legacy model (`main.py`)

Altman-Z, forward dividend yield vs. universe mean, 3yr-avg ROE quartiles, current P/E vs. 5yr-avg P/E. Kept as a "classic" mode in the UI for users who prefer the original formulation.

## 4. Functional requirements

### 4.1 Must-have (P1 → P3)

- **FR-1** Upload a CSV matching the BOS / MOS schema → backend returns a JSON ranking.
- **FR-2** Display ranked watchlist with quartile color-coding (BUY-BUY blue → SELL-SELL red).
- **FR-3** Per-stock detail page showing every factor's raw value, threshold band, sub-score, and contribution to FINAL_SCORE.
- **FR-4** Switch between BOS, MOS, and 4-Factor models on the same uploaded dataset.
- **FR-5** Persist uploads + scoring runs (Postgres) so users can revisit prior recommendations.
- **FR-6** Auth (email magic-link, no password).
- **FR-7** Pluggable data provider interface — CSV first, yfinance second, Bloomberg/Refinitiv via API key later. The scoring engine must not know which provider supplied the row.

### 4.2 Should-have (P4 → P5)

- **FR-8** Backtester: pick a universe + date range → run RBA on each historical snapshot → equity curve + Sharpe + max drawdown.
- **FR-9** Shadow MLA: log ML predictions alongside RBA without exposing them to users.
- **FR-10** Feature store: persist engineered features per stock × date so MLA training and live inference share inputs.

### 4.3 Could-have (P6+)

- **FR-11** SHAP-style explainability per MLA prediction.
- **FR-12** Side-by-side "RBA vs MLA" comparison view with toggle.
- **FR-13** Email/Telegram alerts when a watchlisted stock changes quartile.
- **FR-14** Sector / size / country filters.

### 4.4 Won't-have (v1)

- Order routing, paper-trading simulator, portfolio optimizer, options screener, crypto, FX.

## 5. Non-functional requirements

| Area              | Requirement                                                                               |
|-------------------|-------------------------------------------------------------------------------------------|
| Performance       | < 5 s to score a 1 000-row universe (P2); < 2 s by P6                                     |
| Availability      | 99 % monthly (single-region; we are not a trading-critical system)                        |
| Security          | OWASP Top-10 baseline; no PII beyond email; uploaded CSVs encrypted at rest               |
| Compliance        | UI banner: *"Decision-support only. Not investment advice."* on every recommendation page |
| Auditability      | Every recommendation row stored with `model_version`, `input_snapshot_id`, `timestamp`    |
| Explainability    | RBA: 100 % factor breakdown. MLA: SHAP top-5 features per prediction.                     |
| Data-quality gate | Reject rows where > 30 % of required factor fields are NaN; never silent-fill with 0      |

## 6. System architecture (proposed)

```
trio-web/
├── apps/
│   ├── web/                  # Next.js 16 + React 19 + Tailwind (modeled on Aegis Prime web)
│   └── api/                  # FastAPI service
├── packages/
│   ├── algorithms/           # Pure-Python: bos.py, mos.py, four_factor.py (ported from trio-mvp)
│   │   ├── contracts.py      # Pydantic: ScoreRequest, ScoreResponse, FactorBreakdown
│   │   ├── rba/              # Rule-based engines
│   │   └── mla/              # ML engines (P5+) — same contract
│   ├── data_providers/       # csv.py, yfinance.py, bloomberg.py — uniform interface
│   └── backtester/           # P4
├── infra/
│   └── docker-compose.yml    # api + postgres + redis (cache + Celery later)
└── docs/
    ├── GOAL.md
    ├── PRD.md
    └── algorithms/           # SOPs per algorithm — written before code edits (logic-first rule)
```

**Key contract — `ScoreResponse`** (must remain stable across RBA → MLA swap):
```python
{
  "model_version": "rba-bos-1.0.0",
  "as_of": "2026-04-25T00:00:00Z",
  "universe": "KLCI",
  "results": [
    {
      "ticker": "MAYBANK MK",
      "name": "Malayan Banking Bhd",
      "final_score": 2.45,
      "quartile": 1,                       # 1=BUY-BUY ... 4=SELL-SELL
      "recommendation": "BUY-BUY",
      "factors": [
        {"id": "F4", "label": "Altman Z", "raw": 3.1, "band": "BUY",
         "sub_score": 3, "weight": 0.30, "contribution": 0.90}
      ],
      "explanation": "Strong balance sheet (Altman-Z 3.1) and high dividend yield (6.4%) outweigh below-average analyst sentiment.",
      "source_snapshot_id": "snap_2026-04-25_klci"
    }
  ]
}
```

## 7. RBA → MLA upgrade path

| Step | Description                                                                                                |
|------|------------------------------------------------------------------------------------------------------------|
| M1   | Stand up feature store: every RBA scoring run persists `(ticker, date, raw_factors)` rows                  |
| M2   | Define labels: forward 60-day return, binarized (top-quartile = positive class)                            |
| M3   | Baseline model: gradient-boosted trees (XGBoost / LightGBM) on raw factors + sector + size                 |
| M4   | Walk-forward validation against the same backtest harness used for RBA                                     |
| M5   | Shadow deployment: MLA predictions logged but UI still shows RBA                                           |
| M6   | A/B feature flag: toggle UI between RBA and MLA; surface SHAP explanations for MLA                         |
| M7   | Retraining cadence: monthly, with drift monitoring on factor distributions                                 |

**Hard rule:** MLA cannot ship to users until its backtested net-of-fees return ≥ RBA on the same universe + period.

## 8. UX flows (v1)

1. **Sign in** (magic link).
2. **Upload data** (drag CSV) → *or* **Pick universe** (KLCI default; yfinance pull in P3).
3. **Pick model** — BOS · MOS · 4-Factor (· ML once P6 ships).
4. **Ranking page** — sortable table, quartile chips, sector filter, search.
5. **Stock detail** — factor breakdown table + radar chart (5 factors for BOS) + "Why this score" narrative.
6. **History** — past runs, downloadable as CSV.

## 9. Resolved decisions & open questions

**Resolved (2026-04-25):**
- **R-1** Audience: portfolio / demo project, not a public retail product → no auth marketing, no Stripe, no compliance counsel in v1.
- **R-2** Day-one universes: **KLCI + S&P 500 + universe-agnostic CSV** all on day one. The scoring engine must be universe-blind; only the data-provider layer knows the universe.
- **R-3** Scope commitment: full P0 → P6 roadmap.
- **R-4** Flutter `trio-app` is retired — web only.

**Still open:**
- **OQ-1** Data provider for KLCI — yfinance has thin Bursa coverage. Fall back options: i3investor scraper (already drafted in legacy notebooks), manual Bloomberg CSV export, or paid Refinitiv. Decide before P3.
- **OQ-2** Hosting — Vercel (web) + Render/Fly (api) vs. single VPS Docker compose. Demo polish argues for Vercel; MAS-ecosystem fit argues for self-hosted.
- **OQ-3** Ecosystem placement — keep standalone, fold into `mas-ecosystem`, or expose as a tool to Aegis Prime's Quant-Hypothesis Engine. Revisit at end of P2.
- **OQ-4** Auth in demo — magic-link (PRD §4.1 FR-6) or skip entirely (single-user demo)?
- **OQ-5** MLA model class — gradient-boosted trees only, or also a sequence model (LSTM/transformer) once feature store is rich enough?

## 10. Risks

| Risk                                                                  | Mitigation                                                                  |
|-----------------------------------------------------------------------|-----------------------------------------------------------------------------|
| Bloomberg field names drift / users export from i3investor with different schemas | Schema-validate uploads; surface a "field mapping" UI that maps user columns → canonical fields |
| MLA outperforms RBA in backtest but underperforms live (overfit)      | Walk-forward CV + 6-month shadow mode mandatory before promotion            |
| Users treat recommendations as advice                                 | Persistent disclaimer banner; recommendation page links to methodology page |
| Legal — Malaysian SC regulates investment advice tools                | Decision-support framing; no execution; consult counsel before public launch|
| Free data sources lack KLCI fundamentals depth                        | Allow user-supplied CSV as a permanent first-class input path               |

## 11. Milestones (provisional)

| Milestone | Calendar target | Exit criteria                                                       |
|-----------|-----------------|---------------------------------------------------------------------|
| P0        | 2026-04 (now)   | GOAL.md + PRD.md committed                                          |
| P1        | 2026-05         | `/score` returns BOS/MOS/4F results equivalent to legacy notebooks  |
| P2        | 2026-06         | Web upload → ranking → detail flow demoable                         |
| P3        | 2026-07         | yfinance auto-refresh of KLCI universe                              |
| P4        | 2026-08         | Backtester live                                                     |
| P5        | 2026-10         | MLA shadow logging in production                                    |
| P6        | 2026-12         | MLA promoted behind feature flag                                    |
