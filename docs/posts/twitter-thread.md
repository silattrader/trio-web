<!--
X / TWITTER · 6-tweet thread
Best time: ~9 AM ET on a weekday for fintech audience
Image suggestion: factor radar screenshot (run the app, click any sample stock,
screenshot the radar modal). Or pull a still from docs/demo.mp4.
Each tweet below is under 280 characters; copy-paste in order.
-->

## Tweet 1 of 6 (the hook — must stand alone)

Most "AI stock picker" tools are sales pitches that quietly use today's fundamentals to backtest yesterday's decisions.

Built TRIO Web to fix the lookahead-bias problem.

Open source. Free. 7 factors. Walk-forward verified.
A gate-passed ML model — and the 2 windows where it lost.

🧵

## Tweet 2 of 6

The architecture in one image:

5 RBA engines + 1 gradient-boosted ML, all behind a single JSON contract.

Rule-based ships first. ML can only replace it after backtesting better on the same universe and period — that's an institutional-grade promotion gate, in open source.

[ATTACH IMAGE: factor radar screenshot or architecture diagram]

## Tweet 3 of 6

Point-in-time honesty without a paid Bloomberg/Refinitiv feed:

· SEC EDGAR for fundamentals (Altman Z' from XBRL)
· Form 4 filings for insider flow
· Wikipedia pageview z-score for retail attention (contrarian)
· Financial Modeling Prep for analyst consensus

Every fact is filtered filed ≤ as_of. Zero lookahead.

## Tweet 4 of 6

The gate result, 2022-2023 out-of-sample, model trained 2018-2021:

         RBA    MLA    Lift
TotRet  +9.6%  +26%   +17pp
CAGR    +4.7%  +12.5% +7.8pp
Sharpe   0.33   0.62  +0.29
MaxDD   -19%   -25%   -6pp

Walk-forward 6 windows: MLA wins 4. Mean +11.6pp CAGR.
The 2 losses are in the docs.

## Tweet 5 of 6

"Bring your own keys" is the magic.

No accounts. No Stripe. No SaaS infra to operate.
You paste your free SEC + FMP + Wiki keys into the BYOK panel.
We call providers as you, on your quota.
Multi-tenant safe via per-request contextvars.

Free for everyone, scalable forever.

## Tweet 6 of 6 (the close + ask)

github.com/silattrader/trio-web

Open source. MIT. 154 tests passing.
Built in 3 days. Decision-support, not investment advice.

If you're a fund manager, family office, or robo-advisor curious about a 30-min walk-forward gate run on your universe — DM me.

If you just want to fork it: 🌟 helps.


---

## Single-tweet alternative (if you don't want to thread)

Built TRIO Web: open-source 7-factor equity scoring with a gate-passed ML model. Walk-forward verified across 6 OOS windows (4 wins, mean +11.6pp CAGR). Honest losses in the docs. Bring-your-own-keys, free forever, no Stripe.

github.com/silattrader/trio-web
