<!--
LINKEDIN · long-form post
Best time: Tue-Thu morning local time
Image suggestion: factor radar screenshot or the gate-result table.
The post below is ~1700 chars — sweet spot for above-fold visibility.
Hashtags at the bottom; LinkedIn is mild on hashtags so 3-5 is plenty.
-->

I shipped a thing.

TRIO Web is an open-source 7-factor equity scoring engine with a gate-passed machine-learning model. Two scoring engines on the same JSON contract — rule-based ships first, ML can only replace it after passing a walk-forward backtest on the same universe and period. That's institutional-grade governance, but free and forkable.

Three deliberate architectural choices that make it different:

→ Point-in-time data without a Bloomberg subscription. SEC EDGAR filings, Form 4 insider activity, Wikipedia attention, FMP analyst consensus. All filtered "filed ≤ as_of" so there's zero lookahead bias.

→ Bring-your-own-keys. No accounts, no Stripe, no infrastructure to operate. Users plug in their free API keys; the server calls providers on their quota via per-request contextvars. Multi-tenant safe by design.

→ Honest negative results. The ML model passed the gate at +7.81 pp CAGR lift on 2022-2023 OOS. Walk-forward across 6 rolling windows: 4 wins, 2 losses. The losses are in the docs. Most fintech demos hide that. We publish it because it's how serious researchers signal trust.

If you're at a fund-management shop, family office, robo-advisor, or fintech that wants a 30-minute walk-forward gate run on your universe — that's the conversation I want. Bring your benchmark and your dates; I'll bring the engine.

If you're hiring for quant, quant-eng, or ML-platform roles — three days from concept to a tested, verified, public open-source ML model on real data tells you something about velocity. I'm open to those conversations too.

The repo: https://github.com/silattrader/trio-web
The deck: docs/PITCH.md (in the repo)
The proof: docs/algorithms/mla.md (the gate result + the losses)

#OpenSource #FinTech #QuantitativeFinance #Python #MachineLearning
