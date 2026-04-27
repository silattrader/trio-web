# TRIO Web — 2-minute elevator pitch (investor / B2B)

> **Format:** 4 beats × ~30 seconds. Total runtime 2:00. No slides — voice only.
> **Audience:** angels, family-office partners, fund-management ops leads, B2B
> SaaS investors who understand fintech / quant.
> **Goal:** earn a 30-minute follow-up call. Not to close anything live.

---

## 0:00 — 0:30  ·  The wedge

> Bloomberg charges twenty-four thousand dollars a year per seat for the
> ability to score equities with proper point-in-time fundamentals. A
> Malaysian retail trader can't afford that. So they end up in WhatsApp
> groups taking trade tips that quietly use today's data to back-test
> yesterday's decisions — the lookahead-bias problem nobody is incentivised
> to fix.
>
> **TRIO Web fixes it.** Open-source, free, transparent. Same engine
> serves an EPF retail customer and a KWAP analyst. Different copy, same
> contract.

**Beat:** name a brand the listener trusts as the cost-anchor (Bloomberg).
Land the moral problem (lookahead bias). Position TRIO as the fix.

---

## 0:30 — 1:00  ·  What we built

> Seven equity factors, point-in-time-honest from the ground up. SEC EDGAR
> for fundamentals, Form-4 filings for insider flow, Wikipedia pageview
> z-scores for retail attention, Financial Modeling Prep for analyst
> consensus. All composable, all free at small scale.
>
> Two scoring engines on the same JSON contract: the rule-based one ships
> first; the gradient-boosted ML model can only replace it after passing a
> walk-forward gate on the same universe and period. **That's institutional
> governance, in open source.**

**Beat:** name the components quickly to establish technical credibility.
Then name the architectural innovation (gate). Don't dwell.

---

## 1:00 — 1:30  ·  The proof

> We ran the gate. Twenty-twenty-two through twenty-twenty-three,
> out-of-sample, model trained on twenty-eighteen through twenty-twenty-one.
> The ML model beat the rule-based one by **eight percentage points
> CAGR**, **Sharpe lift of zero-point-three**.
>
> Then we walk-forwarded across six rolling windows. ML beat RBA in **four
> out of six**. We documented the two it lost — including the twenty-twenty-
> three first-half bull leg where it underperformed by twenty-four points.
> Most demos hide losses. We publish them. **That's the difference between
> research and a sales pitch.**

**Beat:** numbers up front, no equivocation. Then immediately surface the
honest losses. The juxtaposition of "we won" + "here's where we lost" is
the credibility hook.

---

## 1:30 — 2:00  ·  The ask

> The repo is public, the deploy is one click away, the code passes one
> hundred forty automated tests. We're not raising capital — we don't
> need to, the BYOK architecture means users plug in their own API keys
> and the marginal infrastructure cost is zero.
>
> What we want: **one B2B pilot.** Bring us your universe, your benchmark,
> your date range. We'll run a walk-forward gate against it live in
> thirty minutes. If the numbers don't hold up, we've cost you thirty
> minutes. If they do, we have a conversation.
>
> github.com/silattrader/trio-web. Star it, fork it, or send me a date.

**Beat:** explicitly disqualify "raising a round" — it's noise the
investor wants filtered out. Replace with a concrete, low-risk, high-
information ask. Give the URL last so it sticks.

---

## Speaker mechanics

| Mechanic | Why |
|---|---|
| **Stand still on the proof beat (1:00–1:30).** | The numbers carry the slide. Don't hand-wave them. |
| **Pause after "we publish them."** | The differentiation lands when the listener has half a second to internalise the contrast with what they're used to. |
| **Don't list the seven factors.** | If they ask, you have them in your pocket. If they don't, you saved twelve seconds. |
| **End with the URL, not "thank you."** | The URL is the action. "Thank you" is filler. |

## Variants by audience

### For an angel investor
Keep above. Substitute "We're not raising capital" with "We may raise a
small pre-seed in Q3 if a B2B pilot validates the demand. Today: just the
pilot ask."

### For a family-office tech lead
Skip beat 0:00–0:15 (Bloomberg framing they already know). Open with: "We
built an open-source equity-scoring stack with an institutional-grade
walk-forward gate. We want to deploy it inside one fund as proof. Five
minutes — does that interest you?"

### For a hiring manager (quant / quant-eng)
Replace beat 1:30–2:00 with: "I'm not pitching a company. I'm pitching
myself. Three days from concept to a gate-passed ML model on real
point-in-time data, with walk-forward verification, fully tested, fully
public. If your team is hiring for that velocity, that's the call."

## Memorisation aid

Each beat, one anchor:

| Beat | Anchor |
|---|---|
| The wedge | "$24,000 a year" |
| What we built | "Walk-forward gate" |
| The proof | "+8 pp CAGR · 4 of 6 windows · we publish the losses" |
| The ask | "30-minute call · your universe · live walk-forward" |

Four numbers, four phrases, two minutes.
