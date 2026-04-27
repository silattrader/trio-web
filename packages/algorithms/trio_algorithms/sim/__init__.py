"""MIROFISH — Multi-agent Investor Reflexivity Out-of-Faction Information SHock.

A swarm-simulation engine that models two factions of market participants
(retail + institutional) and projects how their interaction propagates a
fundamental shock into price action. The output is a per-ticker contagion
score plus a per-step price trajectory.

This is a SCAFFOLD, not a research-grade implementation. The real MIROFISH
(per project memory) involves:
- ATLAS-GIC graph for cross-asset contagion
- Soros reflexivity loop (price affects fundamentals affects price)
- Darwinian agent weighting (agents that win get larger)
- Uncertainty haircut on confidence intervals

The v0 scaffold here implements just the agent + step loop with two factions
and a basic reflexivity feedback. Subsequent sessions extend the model.

SOP: docs/algorithms/mirofish.md
"""
from .agents import InstitutionalAgent, RetailAgent
from .simulator import MirofishResult, MirofishSimulator, simulate_shock

__all__ = [
    "InstitutionalAgent",
    "RetailAgent",
    "MirofishResult",
    "MirofishSimulator",
    "simulate_shock",
]
