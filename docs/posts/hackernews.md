<!--
HACKER NEWS · Show HN
Submit at: https://news.ycombinator.com/submit
Best time: Mon-Wed 7-9 AM Pacific (peak HN traffic)
Title goes in the "title" field, body goes in "text" field.
Stay in the comments for the first 4 hours.
-->

## Title

Show HN: TRIO Web – 7-factor equity scoring with a gate-passed ML model

## URL field

https://github.com/silattrader/trio-web

## Text field

TRIO Web is an open-source factor-scoring engine for equities. Two engines on one JSON contract: a rule-based 7-factor stack (volume, target return, dividend yield, Altman Z, analyst sentiment, insider flow, retail attention) and a gradient-boosted model that can only replace the rule-based default after passing a walk-forward gate.

Three things that might be interesting to this crowd:

1. Point-in-time honesty without a paid feed. SEC EDGAR (XBRL fundamentals + Form 4 insider transactions), Wikipedia pageview z-scores for retail attention, Financial Modeling Prep for analyst consensus. All filtered `filed <= as_of` so there's no lookahead.

2. Bring-your-own-keys architecture. No accounts, no Stripe, no SaaS infra to operate. Users paste their free API keys into a settings panel; the server calls providers as them via per-request contextvars. Multi-tenant safe by design.

3. Honest negative results. The MLA model passed the gate with +7.81 pp CAGR vs RBA on 2022–2023 OOS — but underperformed in 2 of 6 walk-forward windows. Both losses are documented in docs/algorithms/mla.md. Most fintech demos hide that.

Stack: Python 3.12 + FastAPI + scikit-learn for the API; Next.js 15 + TypeScript + Tailwind + recharts for the web. 154 pytest passing, GitHub Actions CI, MIT licensed.

Known limits:
- Curated 28-name universe today. SP500-100 + KLCI-30 added but MLA hasn't been retrained on them yet.
- KLCI gets ~1.5 of 7 factors PIT-honestly today (no SEC analogue for Bursa Malaysia).
- 5-factor vs 7-factor head-to-head was inconclusive — flow factors are within noise on this universe.

Repo: https://github.com/silattrader/trio-web
Architecture deep-dive: docs/algorithms/mla.md
53-second demo: docs/demo.mp4

Happy to answer anything in the comments.
