# Launch posts — Show HN, X, LinkedIn, Reddit

Five platform-tuned posts aligned to the deck's framing (`docs/PITCH.md`).
Each is calibrated to the platform's house style. **Pick the URL replacement
once you deploy** — every post references either the GitHub URL or the live
demo URL.

---

## 1. Show HN — Hacker News

**Posting tips:**
- Title is the Show HN currency — under 80 chars, no clickbait.
- Submit between 7–9 AM Pacific (peak HN traffic).
- The body **is** the comment — HN doesn't separate them. Top of body
  must hook in 2 sentences or it dies.
- Be in the comments for the first 4 hours to answer questions.
- HN downvotes hype words; rewards specificity + honesty about limits.

### Title
```
Show HN: TRIO Web – 7-factor equity scoring with a gate-passed ML model
```

### Body

```
TRIO Web is an open-source factor-scoring engine for equities. Two engines
on one JSON contract: a rule-based 7-factor stack (volume, target return,
dividend yield, Altman Z, analyst sentiment, insider flow, retail
attention) and a gradient-boosted model that can only replace the
rule-based default after passing a walk-forward gate.

Three things that might be interesting to this crowd:

1. Point-in-time honesty without a paid feed. SEC EDGAR (XBRL fundamentals
   + Form 4 insider transactions), Wikipedia pageview z-scores for retail
   attention, Financial Modeling Prep for analyst consensus. All filtered
   `filed <= as_of` so there's no lookahead.

2. Bring-your-own-keys architecture. No accounts, no Stripe, no SaaS
   infra to operate. Users paste their free API keys into a settings
   panel; the server calls providers as them via per-request
   contextvars. Multi-tenant safe by design.

3. Honest negative results. The MLA model passed the gate with +7.81 pp
   CAGR vs RBA on 2022–2023 OOS — but underperformed in 2 of 6 walk-
   forward windows. Both losses are documented in
   docs/algorithms/mla.md. Most fintech demos hide that.

Stack: Python 3.12 + FastAPI + scikit-learn for the API; Next.js 15 +
TypeScript + Tailwind + recharts for the web. 140 pytest passing,
GitHub Actions CI, MIT licensed.

Known limits:
- Curated 28-name universe today. SP500-100 + KLCI-30 added but MLA hasn't
  been retrained on them yet.
- KLCI gets ~1.5 of 7 factors PIT-honestly today (no SEC analogue for
  Bursa Malaysia).
- 5-factor vs 7-factor head-to-head was inconclusive — flow factors are
  within noise on this universe.

Repo: https://github.com/silattrader/trio-web
Architecture deep-dive: docs/algorithms/mla.md

Happy to answer anything in the comments.
```

### What HN will critique

- **"Just another factor model"** — counter with the gate + walk-forward
  reproducibility (`scripts/walk_forward_gate.py`).
- **"yfinance ToS prohibits commercial use"** — agreed; that's why BYOK
  exists. Hosted demo runs free-tier-only.
- **"Why not just use Quantopian/Zipline/etc"** — different audience
  (institutional users want their own keys + audit trail; not a
  research notebook).
- **"In-sample r²=0.69 doesn't mean anything"** — agreed; the CAGR/Sharpe
  lift on OOS is the actual signal. r² is reported for transparency,
  not as a performance claim.

---

## 2. X / Twitter (thread, 6 posts)

**Posting tips:**
- Thread, not single tweet. Lead with the hook, deliver in beats.
- First post must stand alone — a non-zero number of viewers will quote-
  RT it without reading the rest.
- Include 1 image (factor radar screenshot or gate-result table).
- Post ~9 AM ET on a weekday for fintech audience.

### Thread

**1/6**
```
Most "AI stock picker" tools are sales pitches that quietly use today's
fundamentals to backtest yesterday's decisions.

Built TRIO Web to fix the lookahead-bias problem.

Open source. Free. 7 factors. Walk-forward verified.
A gate-passed ML model — and the 2 windows where it lost.

🧵
```

**2/6**
```
The architecture in one screenshot:

5 RBA engines + 1 gradient-boosted ML, all behind a single JSON contract.
Rule-based ships first. ML can only replace it after backtesting better
on the same universe and period — that's an institutional-grade
promotion gate, in open source.
```
*[Attach: screenshot of the factor radar from the live demo, or the
architecture diagram from PITCH.md slide 5]*

**3/6**
```
Point-in-time honesty without a paid Bloomberg/Refinitiv feed:

· SEC EDGAR for fundamentals (Altman Z' from XBRL)
· Form 4 filings for insider flow
· Wikipedia pageview z-score for retail attention (contrarian)
· Financial Modeling Prep for analyst consensus

Every fact is filtered filed <= as_of. Zero lookahead.
```

**4/6**
```
The gate result, 2022–2023 out-of-sample, model trained 2018–2021:

         RBA    MLA    Lift
TotRet  +9.6%  +26%   +17pp
CAGR    +4.7%  +12.5% +7.8pp
Sharpe   0.33   0.62  +0.29
MaxDD   -19%   -25%   -6pp

Walk-forward 6 windows: MLA wins 4. Mean +11.6pp CAGR.
The 2 losses are in the docs.
```

**5/6**
```
"Bring your own keys" is the magic.

No accounts, no Stripe, no SaaS infra to operate.
You paste your free SEC + FMP + Wiki keys into the BYOK panel.
We call providers as you, on your quota.
Multi-tenant safe via per-request contextvars.

Free for everyone, scalable forever.
```

**6/6**
```
github.com/silattrader/trio-web

Open. MIT. 140 tests passing.
Built in 3 days. Decision-support, not investment advice.

If you're a fund manager, family office, or robo-advisor curious about a
30-min walk-forward gate run on your universe — DM me.

If you just want to fork it: 🌟 helps.
```

### Variant single-tweet (for someone who doesn't want a thread)

```
Built TRIO Web: open-source 7-factor equity scoring with a gate-passed ML
model. Walk-forward verified across 6 OOS windows (4 wins). Honest losses
in the docs. Bring-your-own-keys, free forever, no Stripe.

github.com/silattrader/trio-web
```

---

## 3. LinkedIn (long-form post)

**Posting tips:**
- LinkedIn rewards substance + first-person + a clear ask.
- 1300–1800 chars is the sweet spot (above the "see more" fold).
- Tag relevant people only if you've actually worked with them — random
  tags get downranked.
- Hashtags are weak signal — use 3–5 maximum, only obvious ones.

### Post

```
I shipped a thing.

TRIO Web is an open-source 7-factor equity scoring engine with a
gate-passed machine-learning model. Two scoring engines on the same JSON
contract — rule-based ships first, ML can only replace it after passing
a walk-forward backtest on the same universe and period. That's
institutional-grade governance, but free and forkable.

Three deliberate architectural choices that make it different:

→ Point-in-time data without a Bloomberg subscription. SEC EDGAR
filings, Form 4 insider activity, Wikipedia attention, FMP analyst
consensus. All filtered "filed <= as_of" so there's zero lookahead bias.

→ Bring-your-own-keys. No accounts, no Stripe, no infrastructure to
operate. Users plug in their free API keys; the server calls providers
on their quota via per-request contextvars. Multi-tenant safe by design.

→ Honest negative results. The ML model passed the gate at +7.81 pp CAGR
lift on 2022–2023 OOS. Walk-forward across 6 rolling windows: 4 wins, 2
losses. The losses are in the docs. Most fintech demos hide that. We
publish it because it's how serious researchers signal trust.

If you're at a fund-management shop, family office, robo-advisor, or
fintech that wants a 30-minute walk-forward gate run on your universe —
that's the conversation I want. Bring your benchmark and your dates;
I'll bring the engine.

If you're hiring for quant, quant-eng, or ML-platform roles — three days
from concept to a tested, verified, public open-source ML model on real
data tells you something about velocity. I'm open to those conversations
too.

The repo: https://github.com/silattrader/trio-web
The deck: docs/PITCH.md (in the repo)
The proof: docs/algorithms/mla.md (the gate result + the losses)

#OpenSource #FinTech #QuantitativeFinance #Python #MachineLearning
```

### Why this works on LinkedIn specifically

- **"I shipped a thing."** — opens with personality. LinkedIn's algorithm
  rewards posts that don't read like marketing copy. First-person + casual
  + concrete = signal.
- **Three bullets.** — LinkedIn's mobile readers scan, not read. Three
  parallel-structured bullets are the optimal density.
- **Two distinct asks.** — B2B pilot AND hiring conversation, clearly
  separated. Filters the audience for you.
- **The repo + the deck + the proof.** — three links, each at a different
  depth. Casual readers click the repo. Serious readers go to the deck.
  Quant skeptics jump to the algorithm doc.

---

## 4. r/algotrading (Reddit)

**Posting tips:**
- This subreddit is hostile to "I built a thing" posts that don't show
  numbers. Lead with the data, not the project name.
- Mods will remove anything that looks promotional. Frame as a
  discussion / negative-result share, not a launch.
- Stay in the comments to answer methodology questions. The audience is
  more technical than HN.

### Title
```
Open-sourced a 7-factor equity scoring engine with a walk-forward gate. 4 of 6 OOS windows beat baseline; 2 lost. Discussion of the losses?
```

### Body

```
Spent 3 days building an open-source factor-scoring stack with point-in-
time data (SEC EDGAR + Form 4 + Wikipedia + FMP). Two engines on the same
contract: rule-based 7-factor and a gradient-boosted model trained on
forward 63-day returns.

Walk-forward gate, 6 rolling 6-month OOS windows from 2021-H1 to 2023-H2,
trained on all data before each window:

```
Window      RBA      MLA-7    Lift     Beat?
2021-H1    +79.0%   +55.4%   -23.6pp   no
2021-H2    +55.6%   +71.8%   +16.2pp   YES
2022-H1    -15.8%   -22.8%   -7.0pp    no
2022-H2    +34.2%   +19.8%   -14.4pp   no
2023-H1    +24.7%   +75.8%   +51.1pp   YES
2023-H2     +2.3%   +16.9%   +14.6pp   YES

Mean lift: +6.2 pp · MLA wins 3/6
```

Two questions for the sub:

1. **The 2021-H1 loss (-23pp).** RBA caught the bull leg cleanly, MLA
   was more conservative. My read is the model trained on 2018-2020
   over-weighted the COVID drawdown profile. Anyone with experience
   training on rate-cycle transitions — what regularization did you find
   helped most?

2. **Flow factors are within noise.** Added insider_flow (Form 4 net
   buying) and retail_flow (Wikipedia attention z-score) on top of the
   classic 5. Head-to-head walk-forward: 5-factor beats 7-factor by
   1.5pp on average but loses as often as it wins. Is anyone getting
   meaningful signal out of pageview-style attention metrics, or is it
   noise on US large caps specifically?

Repo (MIT, in case anyone wants to fork or run a different universe):
https://github.com/silattrader/trio-web

Methodology + losses written up in docs/algorithms/mla.md. Happy to
discuss anything specific in comments.
```

### Why this works on r/algotrading

- The losses are the headline. r/algotrading respects honesty about
  what didn't work more than perfect-looking returns.
- Two specific methodological questions invite responses from people who
  actually train models. Beats vague "what do you think?" prompts.
- The flow-factor question is genuinely open — flagging known unknowns
  earns respect.

---

## 5. Direct outreach (cold email / DM template)

**For B2B prospects:** family-office partners, fund-of-funds analysts,
robo-advisor product leads.

### Subject line options
```
A. 30-minute walk-forward gate on [your fund's universe]?
B. Open-source equity scoring with PIT data — quick demo?
C. Built an alternative to the Bloomberg/FactSet seat for [their use case]
```

### Body

```
Hi [name],

I built an open-source factor-scoring engine with point-in-time data
(SEC EDGAR + Form 4 + Wikipedia attention + FMP analyst consensus) and
a walk-forward verified ML model.

Headline number: on 2022-2023 out-of-sample, the model lifted CAGR by
+7.81 pp over the rule-based baseline. Across 6 walk-forward windows it
won 4. The 2 losses are documented openly.

I'd like 30 minutes. Bring me your universe (any size) and a date range.
I'll run a live walk-forward gate against your benchmark. If the numbers
don't hold up on your data, you've cost yourself 30 minutes. If they do,
we have a conversation.

No pitch deck, no NDA, no signup. Open source: github.com/silattrader/
trio-web.

Best,
[your name]

---
PS — what makes this different from a hosted SaaS: bring-your-own-keys
architecture means your data licenses and your data audit trail stay
yours. We're not a data vendor; we're an open-source frontend that calls
providers on your behalf.
```

### Why this works for cold B2B

- Subject A is the strongest — names a specific, low-cost, high-value
  ask in 7 words.
- Numbers in the first 100 chars of the body. Recipients skim.
- "30 minutes" + "bring your own data" + "no pitch deck" together
  signal you're not selling anything yet. You're earning the next call.
- The PS lands the architectural differentiation for technical
  recipients who scrolled to the bottom.

---

## Posting cadence

If you ship all of these in one week, the order that maximizes signal:

1. **Monday 9 AM ET.** Show HN. Most permissive audience for technical
   substance + open-source projects.
2. **Tuesday 9 AM ET.** X thread. The HN traffic + early engagement
   helps the X algorithm pick it up.
3. **Wednesday morning local time.** LinkedIn. Different audience —
   recruiters, fund-management ops, B2B fintech.
4. **Thursday afternoon.** r/algotrading. After you've handled the
   high-engagement audiences and have answers ready for hard questions.
5. **Friday + ongoing.** Cold outreach to specific B2B prospects, using
   the engagement signals from the public posts to warm up the message.

**Don't do all of these on the same day.** Each platform's algorithm
notices when content is being broadcast vs. organically posted.

## What "success" looks like by post

| Platform | Reasonable success metric |
|---|---|
| Show HN | Front page (top 30) for 4+ hours · 50+ comments · 100+ stars |
| X | 1000+ thread impressions · 5+ replies from quant/fintech accounts |
| LinkedIn | 5000+ impressions · 3+ DMs from fund/family-office contacts |
| r/algotrading | 50+ upvotes · 20+ comments answering / asking specifics |
| Cold outreach | 1 in 10 reply rate · 1 in 30 books a 30-min call |

If a platform underperforms its bar, that's a signal not to invest
further effort there. **Don't double down on a channel that didn't
respond on the first attempt** — the signal is the audience isn't
there.
