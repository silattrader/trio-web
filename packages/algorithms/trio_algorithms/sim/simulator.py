"""MIROFISH simulator — orchestrates a swarm of agents through N steps
in response to a fundamental shock and projects the resulting price path.

The v0 model is intentionally simple:

1. Initial price = 100. Apply a one-shot fundamental shock at step 0
   (e.g. the fundamental_anchor jumps from 1.0 to 1.3, signalling overvaluation).
2. At each step, every agent gets a `MarketContext` snapshot and returns a
   `TradeIntent`.
3. Net intents → price impact via a square-root liquidity model.
4. Sentiment_z drifts up when retail flow is net-buying (reflexivity).
5. Recent momentum updates from the trailing 5 steps' returns.

Output: a per-step price trajectory + a "contagion score" summarising peak
deviation from the fundamental anchor.

Real MIROFISH would extend this with:
- ATLAS-GIC graph propagation across correlated tickers
- Soros reflexivity: fundamental_anchor mutates as price moves (positive
  feedback loop)
- Darwinian agent weighting: winning agents attract more capital next step
- Uncertainty haircut: agent confidence shrinks in high-volatility regimes

Those are the next-session deliverables. The v0 here gives a working
skeleton that returns interpretable numbers on a single ticker.
"""
from __future__ import annotations

import math
import random
import statistics as stats
from dataclasses import dataclass, field

from .agents import Agent, InstitutionalAgent, MarketContext, RetailAgent


@dataclass
class MirofishResult:
    """Per-ticker simulation outcome."""

    ticker: str
    n_steps: int
    initial_price: float
    final_price: float
    price_path: list[float]
    peak_deviation_pct: float       # max |price - initial| / initial × 100
    fundamental_anchor: float
    institutional_share: float       # fraction of step-end position held by institutional faction
    contagion_score: float            # 1.0 = strong contagion likely; 0 = none
    warnings: list[str] = field(default_factory=list)


def _price_impact(net_dollar_flow: float, total_capital: float) -> float:
    """Square-root market-impact model: Δ_pct ≈ k × sign × √(|flow| / capital).

    Calibrated so a net flow equal to 1% of capital moves price by ~1%.
    """
    if total_capital <= 0:
        return 0.0
    sign = 1.0 if net_dollar_flow >= 0 else -1.0
    fraction = abs(net_dollar_flow) / total_capital
    return sign * math.sqrt(fraction) * 0.10  # 0.10 calibrates the impact


@dataclass
class MirofishSimulator:
    """Orchestrates N steps of agent decisions + price impact."""

    agents: list[Agent]
    initial_price: float = 100.0
    fundamental_anchor: float = 1.0
    seed: int = 42

    def run(
        self,
        ticker: str,
        n_steps: int = 30,
        initial_sentiment_z: float = 0.0,
    ) -> MirofishResult:
        rng = random.Random(self.seed)
        price = self.initial_price
        sentiment_z = initial_sentiment_z
        recent_returns: list[float] = []
        path = [price]
        warnings: list[str] = []

        # Initial capital snapshot for the institutional-share calc at step end.
        total_capital_initial = sum(a.capital for a in self.agents)
        if total_capital_initial == 0:
            warnings.append("zero total capital across agents — nothing to do")

        for step in range(n_steps):
            recent_momentum = stats.mean(recent_returns) if recent_returns else 0.0
            ctx = MarketContext(
                ticker=ticker, price=price,
                fundamental_anchor=self.fundamental_anchor,
                sentiment_z=sentiment_z,
                recent_momentum=recent_momentum,
                institutional_pressure=0.0,  # populated post-step in v1
                step=step, rng=rng,
            )

            intents = []
            for agent in self.agents:
                intent = agent.decide(ctx)
                intents.append((agent, intent))
                # Apply the trade to the agent's books.
                agent.position += intent.size
                agent.capital -= intent.size * price

            # Net dollar flow (positive = net buying = upward price impact).
            net_dollar = sum(intent.size * price for _, intent in intents)
            # Square-root liquidity impact on price.
            denominator = max(total_capital_initial, 1.0)
            delta_pct = _price_impact(net_dollar, denominator)
            price = price * (1.0 + delta_pct)
            path.append(price)

            # Update rolling momentum (5-step window).
            ret = delta_pct
            recent_returns.append(ret)
            if len(recent_returns) > 5:
                recent_returns.pop(0)

            # Reflexivity-lite: sentiment_z drifts toward sign(net_dollar)
            # — when buying continues, attention rises.
            sentiment_z = 0.7 * sentiment_z + 0.3 * (1.0 if net_dollar > 0 else -0.5)

        # Compute outcomes.
        final_price = price
        peak_dev_pct = max(abs(p - self.initial_price) for p in path) / self.initial_price * 100

        inst_position = sum(
            a.position for a in self.agents if isinstance(a, InstitutionalAgent)
        )
        total_position = sum(abs(a.position) for a in self.agents) or 1.0
        institutional_share = inst_position / total_position

        # Contagion score: a heuristic in [0, 1] combining
        # peak deviation relative to anchor + institutional retreat.
        anchor_distance = abs(self.fundamental_anchor - final_price / self.initial_price)
        contagion_score = min(1.0, peak_dev_pct / 30.0 + anchor_distance / 1.0)

        return MirofishResult(
            ticker=ticker, n_steps=n_steps,
            initial_price=self.initial_price, final_price=final_price,
            price_path=path,
            peak_deviation_pct=round(peak_dev_pct, 2),
            fundamental_anchor=self.fundamental_anchor,
            institutional_share=round(institutional_share, 3),
            contagion_score=round(contagion_score, 3),
            warnings=warnings,
        )


def simulate_shock(
    ticker: str,
    fundamental_anchor: float = 1.0,
    initial_sentiment_z: float = 0.0,
    n_steps: int = 30,
    seed: int = 42,
) -> MirofishResult:
    """Convenience wrapper: builds a default 2-faction swarm + runs the sim.

    Default agents:
    - 100 retail agents, each with $10k → $1M total retail capital
    - 5 institutional agents, each with $200M → $1B total institutional capital

    The institutional faction is 1000× bigger by capital but slow-moving,
    while retail moves faster and reacts to attention signals.
    """
    retail = [
        RetailAgent(name=f"retail_{i}", capital=10_000) for i in range(100)
    ]
    institutional = [
        InstitutionalAgent(name=f"inst_{i}", capital=200_000_000) for i in range(5)
    ]
    sim = MirofishSimulator(
        agents=retail + institutional,
        fundamental_anchor=fundamental_anchor,
        seed=seed,
    )
    return sim.run(ticker=ticker, n_steps=n_steps,
                   initial_sentiment_z=initial_sentiment_z)
