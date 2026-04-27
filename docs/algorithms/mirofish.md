# SOP — MIROFISH (v0 Scaffold)

**Status:** v0 scaffold — working but minimal. Multi-session research roadmap below.
**Source of truth:** `packages/algorithms/trio_algorithms/sim/`
**Endpoint:** `POST /simulate`

## What MIROFISH is

> **M**ulti-agent **I**nvestor **R**eflexivity **O**ut-of-**F**action
> **I**nformation **SH**ock — a swarm-simulation engine that models how
> a fundamental shock propagates into price action through the
> interaction of two market-participant factions:

| Faction | Capital | Speed | Signal |
|---|---|---|---|
| **Retail** | small (~$10k each, ~100 agents → $1M total) | fast, reactive | momentum × attention × noise |
| **Institutional** | large (~$200M each, ~5 agents → $1B total) | slow, contrarian | fundamental anchor − attention spike |

Both factions act every step; the simulator nets their trades into a
square-root market-impact model and updates price + sentiment. Repeat
N steps → output a price trajectory + a contagion score.

## Why this exists in TRIO

The existing engines (BOS, BOS-Flow, QV, MLA) all answer a *static*
question: **"is this stock attractive right now?"** MIROFISH answers a
*dynamic* one: **"if news hits, how does the crowd react?"**

Specific use cases the existing engines can't address:

- A retail-attention spike (NVDA-style 2023 z=+5.85) — does it propagate
  far enough to drag price away from fundamentals?
- A fundamental shock (downgrade, earnings miss) — how fast do
  institutionals fade in vs how fast does retail panic out?
- Quality-flight regime detection — when retail capitulates, do
  institutions rotate in (mean-reverting opportunity) or follow
  (momentum capitulation)?

## v0 model

### Agents

`packages/algorithms/trio_algorithms/sim/agents.py`

**RetailAgent**
```
signal = (fomo or panic factor) × recent_momentum × |sentiment_z|
       + Gaussian noise (Reddit / TikTok effect)
```
- `fomo_factor=1.5` — buys faster on positive momentum
- `panic_factor=2.0` — sells faster on negative momentum (loss aversion)
- Position-sizing: max 5% of capital per step
- Ignores fundamental_anchor entirely

**InstitutionalAgent**
```
signal = -fundamental_weight × (anchor − 1.0)            # buy cheap, sell expensive
       - attention_aversion × max(sentiment_z − 1.0, 0)  # contrarian to spikes
```
- Position-sizing capped at `max_step_pct=1.0%` of capital per step
- Ignores intra-step momentum
- Reacts to attention-spike contrarianly

### Simulator

`packages/algorithms/trio_algorithms/sim/simulator.py`

For each of N steps:
1. Build `MarketContext(price, anchor, sentiment_z, recent_momentum, ...)`
2. Each agent returns a `TradeIntent(size, confidence, rationale)`
3. Apply trades to agent positions and capital
4. Compute net dollar flow → square-root price impact:
   `Δ_pct = sign × √(|flow| / total_capital) × 0.10`
5. Update sentiment_z via reflexivity (drifts toward sign of net flow)
6. Roll the 5-step momentum window

### Outputs

`MirofishResult` carries:
- `price_path`: list of (n_steps + 1) prices
- `peak_deviation_pct`: max |price − initial| / initial × 100
- `institutional_share`: fraction of total position held by institutional
  faction at simulation end
- `contagion_score` ∈ [0, 1]: heuristic combining peak deviation +
  anchor-distance. **0.05 ≈ benign**, **0.5+ ≈ meaningful contagion likely**

## Endpoint

```bash
curl -X POST http://localhost:8001/simulate \
  -H 'content-type: application/json' \
  -d '{
    "ticker": "NVDA",
    "fundamental_anchor": 1.2,
    "initial_sentiment_z": 4.0,
    "n_steps": 30,
    "seed": 42
  }'
```

Returns:
```json
{
  "ticker": "NVDA",
  "n_steps": 30,
  "initial_price": 100.0,
  "final_price": 85.32,
  "price_path": [100.0, 99.8, ...],
  "peak_deviation_pct": 18.4,
  "fundamental_anchor": 1.2,
  "institutional_share": 0.342,
  "contagion_score": 0.812,
  "warnings": []
}
```

## Honest scope of v0

**What works today:**
- Two-faction agent architecture
- Square-root market-impact model
- Reflexivity-lite (sentiment drifts with net flow)
- Deterministic via fixed seed (testable)
- 15 unit tests passing

**What's deliberately not in v0** (multi-session future work, per the
research-mirofish memory file):

| Missing piece | What it'd add |
|---|---|
| **ATLAS-GIC graph** | Cross-asset contagion — a shock to one ticker propagates to correlated ones. Today the simulator runs on a single ticker in isolation. |
| **Soros reflexivity loop** | Today's reflexivity is sentiment-only. Real reflexivity has price → fundamental_anchor mutation (overpriced stocks get fewer customers, fundamentals worsen, price falls more). Self-reinforcing. |
| **Darwinian agent weighting** | Agents that win get more capital next step; losers get less. Captures momentum carrying capacity over time. |
| **Uncertainty haircut** | Agent confidence shrinks in high-volatility regimes; large agents pull back when intra-step variance rises. |
| **Live integration with TRIO data** | Today the `fundamental_anchor` parameter is hand-set (1.0 = fair, >1 = overvalued). Should ingest from `score_qv` / `score_mla_v0` outputs and translate the score into an anchor automatically. |
| **Multi-ticker / portfolio-level** | Single-ticker today. Real use case is: "across my universe, where does contagion bite hardest?" |
| **Web UI** | No frontend yet. Plot the price trajectory + contagion banner + faction breakdown. |

## Plumbing notes

- The simulator imports `random.Random` for deterministic seeding — pure
  Python stdlib. Zero new dependencies on top of what TRIO already pulls.
- The `Agent` protocol means new factions can be added without modifying
  the simulator (e.g. a `MarketMakerAgent` for liquidity provision, or
  an `ActivistAgent` for position-sizing).
- All agent decisions are stateless w.r.t. global market state; agents
  only see the `MarketContext` snapshot. Easy to parallelise later.

## Connection to retail/institutional faction signal in TRIO

The existing `RetailFlowPitProvider` (Wikipedia z-score) and
`InsiderFlowPitProvider` (Form 4) emit **observed** retail/institutional
*activity*. MIROFISH simulates **predicted** retail/institutional
*reaction* given a hypothetical shock.

Combined, they form a two-tier crowd model:
- **Today's state** ← from the flow factors (signal capture)
- **Tomorrow's reaction** ← from the simulator (signal projection)

## Tests

`apps/api/tests/test_mirofish.py` — 15 tests covering:
- Per-agent decision logic (retail FOMO + panic; institutional contrarian)
- Position-sizing caps
- Simulator determinism with fixed seed
- /simulate endpoint round-trip
- Validation on anchor + step ranges

## References

The MIROFISH name + research direction trace to the user's
`research_mirofish.md` memory file (referenced in
`project_eagle_eye_mirofish_pitch.md`). Key conceptual debts:

- **Soros, G. (1987)** *The Alchemy of Finance* — reflexivity loop.
- **Brock & Hommes (1998)** — heterogeneous-agent market models.
- **LeBaron (2006)** — agent-based computational finance.
- **Cont & Bouchaud (2000)** — herding behaviour and fat-tail returns.
