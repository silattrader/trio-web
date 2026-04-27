"""Agent classes for the MIROFISH swarm.

Two factions, deliberately stylised:

- ``RetailAgent``: small capital, high attention sensitivity, herd behaviour.
  Decision driven by sentiment + recent price momentum + crowd pressure.
- ``InstitutionalAgent``: large capital, fundamentals-driven, slow-moving,
  liquidity-aware. Decision driven by fundamental anchor (RBA/QV score) +
  position-sizing constraints.

Both agents implement the same protocol: ``decide(context) → trade_intent``.
The simulator orchestrates the order-of-operations.

This file is part of the v0 scaffold. The real behavioural distinctions
between these factions are an active research direction (per
docs/algorithms/mirofish.md).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol


@dataclass
class MarketContext:
    """Snapshot of market state passed to each agent at every step."""

    ticker: str
    price: float
    fundamental_anchor: float       # 1.0 = fairly valued; >1 = overvalued
    sentiment_z: float              # crowd attention z-score (retail flow proxy)
    recent_momentum: float          # rolling 5-step return
    institutional_pressure: float   # net institutional buying signal in [-1, 1]
    step: int
    rng: random.Random


@dataclass
class TradeIntent:
    """An agent's intent for one step. Positive size = buy, negative = sell.

    Size is in shares. The simulator normalises against capital before
    applying to price impact.
    """

    size: float
    confidence: float = 1.0  # used for darwinian weighting in v1+
    rationale: str = ""


class Agent(Protocol):
    """Minimal protocol both factions implement."""

    name: str
    capital: float
    position: float       # current position in shares

    def decide(self, ctx: MarketContext) -> TradeIntent: ...


# --------------------------------------------------------------------------
# Retail Agent
# --------------------------------------------------------------------------


@dataclass
class RetailAgent:
    """Small-cap, high-attention, momentum-following, weak fundamentals.

    Heuristics:
    - Buys on positive momentum × sentiment_z (FOMO).
    - Sells on negative momentum × sentiment_z (panic).
    - Position-sizing: % of capital scaled by confidence.
    - Ignores fundamental_anchor (mostly).
    - Has random noise (Reddit-tip / TikTok-effect).
    """

    name: str
    capital: float
    position: float = 0.0
    fomo_factor: float = 1.5        # how much momentum amplifies the buy signal
    panic_factor: float = 2.0       # asymmetric — sells faster than buys
    noise_amplitude: float = 0.10   # random noise injected into decision

    def decide(self, ctx: MarketContext) -> TradeIntent:
        # Composite signal: momentum × |sentiment|, asymmetric on the downside.
        # Retail loss-aversion makes panic-selling stronger than fomo-buying.
        # Attention magnitude (|s|) amplifies the signal regardless of sign.
        # Floor at 0.5 so quiet-attention names still trade (a bit).
        m = ctx.recent_momentum
        s = ctx.sentiment_z
        attention_amp = max(abs(s), 0.5)
        if m >= 0:
            signal = self.fomo_factor * m * attention_amp
        else:
            signal = self.panic_factor * m * attention_amp   # m<0 → signal<0

        # Inject noise (Reddit / TikTok effect).
        signal += ctx.rng.gauss(0, self.noise_amplitude)

        # Clip to the agent's capacity. Maximum trade per step ~ 5% of capital.
        max_dollar = self.capital * 0.05
        intended_dollars = signal * max_dollar
        size = intended_dollars / max(ctx.price, 0.01)

        # Don't sell more than you hold.
        if size < 0:
            size = max(size, -self.position)

        return TradeIntent(
            size=size,
            confidence=min(1.0, abs(signal)),
            rationale=f"retail momentum={m:.2f} sentiment_z={s:.2f}",
        )


# --------------------------------------------------------------------------
# Institutional Agent
# --------------------------------------------------------------------------


@dataclass
class InstitutionalAgent:
    """Large-cap, fundamentals-driven, contrarian to extreme attention.

    Heuristics:
    - Buys when fundamental_anchor < 1.0 (undervalued) AND retail isn't piling in.
    - Sells when fundamental_anchor > 1.0 (overvalued) OR retail attention spikes.
    - Position-sizing: very gradual — at most 1% of capital per step.
    - Fully ignores intra-step momentum (uses only structural signals).
    """

    name: str
    capital: float
    position: float = 0.0
    fundamental_weight: float = 1.0
    attention_aversion: float = 0.5   # contrarian sensitivity to retail spikes
    max_step_pct: float = 0.01        # hard ceiling per step

    def decide(self, ctx: MarketContext) -> TradeIntent:
        # Anchor: how far from "fair" is price? +ve gap = overvalued.
        gap = ctx.fundamental_anchor - 1.0
        # Buy when gap is negative (cheap), sell when positive (expensive).
        signal = -self.fundamental_weight * gap

        # Contrarian to retail attention spikes — fade extreme sentiment.
        signal -= self.attention_aversion * max(ctx.sentiment_z - 1.0, 0)

        # Throttle to max_step_pct of capital.
        max_dollar = self.capital * self.max_step_pct
        intended_dollars = max(min(signal, 1.0), -1.0) * max_dollar
        size = intended_dollars / max(ctx.price, 0.01)

        if size < 0:
            size = max(size, -self.position)

        return TradeIntent(
            size=size,
            confidence=min(1.0, abs(signal)),
            rationale=f"institutional gap={gap:+.2f} att_z={ctx.sentiment_z:+.2f}",
        )
