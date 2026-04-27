"""MIROFISH swarm-sim tests — deterministic via fixed seed."""
from __future__ import annotations

import random

from fastapi.testclient import TestClient

from app.main import app
from trio_algorithms import (
    InstitutionalAgent,
    MirofishSimulator,
    RetailAgent,
    simulate_shock,
)
from trio_algorithms.sim.agents import MarketContext

client = TestClient(app)


# --- agent unit tests -------------------------------------------------


def test_retail_agent_buys_on_positive_momentum_and_sentiment():
    agent = RetailAgent(name="r1", capital=10_000)
    ctx = MarketContext(
        ticker="X", price=100, fundamental_anchor=1.0,
        sentiment_z=2.0, recent_momentum=0.05, institutional_pressure=0,
        step=0, rng=random.Random(1),
    )
    intent = agent.decide(ctx)
    assert intent.size > 0
    assert "retail" in intent.rationale


def test_retail_agent_panics_on_negative_momentum_and_sentiment():
    agent = RetailAgent(name="r2", capital=10_000, position=50)
    ctx = MarketContext(
        ticker="X", price=100, fundamental_anchor=1.0,
        sentiment_z=-2.0, recent_momentum=-0.10, institutional_pressure=0,
        step=0, rng=random.Random(1),
    )
    intent = agent.decide(ctx)
    assert intent.size < 0


def test_institutional_agent_buys_undervalued():
    agent = InstitutionalAgent(name="i1", capital=200_000_000)
    ctx = MarketContext(
        ticker="X", price=100, fundamental_anchor=0.7,    # undervalued
        sentiment_z=0.0, recent_momentum=0.02, institutional_pressure=0,
        step=0, rng=random.Random(1),
    )
    intent = agent.decide(ctx)
    assert intent.size > 0


def test_institutional_agent_sells_overvalued_and_attention_spike():
    agent = InstitutionalAgent(name="i2", capital=200_000_000, position=10000)
    ctx = MarketContext(
        ticker="X", price=100, fundamental_anchor=1.4,    # overvalued
        sentiment_z=3.0,                                  # extreme attention
        recent_momentum=0.0, institutional_pressure=0,
        step=0, rng=random.Random(1),
    )
    intent = agent.decide(ctx)
    assert intent.size < 0


def test_institutional_agent_capped_at_max_step_pct():
    agent = InstitutionalAgent(
        name="i3", capital=1_000_000, max_step_pct=0.01,
    )
    ctx = MarketContext(
        ticker="X", price=100, fundamental_anchor=0.1,    # extreme undervalue
        sentiment_z=0.0, recent_momentum=0.0, institutional_pressure=0,
        step=0, rng=random.Random(1),
    )
    intent = agent.decide(ctx)
    # Cap = 1% of $1M = $10K = 100 shares at $100 each. Should not exceed.
    assert abs(intent.size * 100) <= 10_000 + 1


# --- simulator unit tests --------------------------------------------


def test_simulate_shock_is_deterministic():
    """Same seed → same trajectory."""
    a = simulate_shock("AAPL", fundamental_anchor=1.2, n_steps=20, seed=42)
    b = simulate_shock("AAPL", fundamental_anchor=1.2, n_steps=20, seed=42)
    assert a.price_path == b.price_path
    assert a.contagion_score == b.contagion_score


def test_simulate_shock_different_seeds_diverge():
    a = simulate_shock("AAPL", fundamental_anchor=1.2, n_steps=30, seed=1)
    b = simulate_shock("AAPL", fundamental_anchor=1.2, n_steps=30, seed=999)
    # Trajectory differs after a few steps due to RNG noise.
    assert a.price_path[-1] != b.price_path[-1]


def test_simulate_shock_steps_roundtrip():
    n = 25
    res = simulate_shock("AAPL", n_steps=n, seed=0)
    # Path length = n_steps + 1 (initial + every step end).
    assert len(res.price_path) == n + 1
    assert res.n_steps == n


def test_simulate_shock_overvalued_drives_negative_pressure():
    """A strongly overvalued anchor should produce institutional selling
    and a final price below initial more often than not."""
    res = simulate_shock("X", fundamental_anchor=1.8, n_steps=50, seed=42)
    # We don't assert direction strictly (random walk), but the contagion
    # score should be non-trivial when the anchor is far from 1.
    assert res.contagion_score > 0.05


def test_simulate_shock_emits_contagion_score_in_range():
    res = simulate_shock("X", fundamental_anchor=1.3, n_steps=30, seed=7)
    assert 0.0 <= res.contagion_score <= 1.0


# --- /simulate endpoint ---------------------------------------------


def test_simulate_endpoint_default_request():
    body = client.post("/simulate", json={"ticker": "AAPL"}).json()
    assert body["ticker"] == "AAPL"
    assert body["n_steps"] == 30
    assert body["initial_price"] == 100.0
    assert len(body["price_path"]) == 31
    assert 0.0 <= body["contagion_score"] <= 1.0


def test_simulate_endpoint_custom_anchor_and_sentiment():
    body = client.post("/simulate", json={
        "ticker": "GME",
        "fundamental_anchor": 2.5,        # extreme overvaluation
        "initial_sentiment_z": 4.0,       # huge attention spike
        "n_steps": 50,
        "seed": 1,
    }).json()
    assert body["ticker"] == "GME"
    assert body["fundamental_anchor"] == 2.5
    assert len(body["price_path"]) == 51


def test_simulate_endpoint_validates_anchor_range():
    body = client.post("/simulate", json={"ticker": "X", "fundamental_anchor": 0.05})
    assert body.status_code == 422


def test_simulate_endpoint_validates_steps_range():
    body = client.post("/simulate", json={"ticker": "X", "n_steps": 1})
    assert body.status_code == 422
    body = client.post("/simulate", json={"ticker": "X", "n_steps": 500})
    assert body.status_code == 422


def test_custom_simulator_with_explicit_agents():
    """Sanity test: build a sim manually without using simulate_shock()."""
    agents = [
        RetailAgent(name="r", capital=50_000),
        InstitutionalAgent(name="i", capital=100_000_000),
    ]
    sim = MirofishSimulator(agents=agents, fundamental_anchor=1.5, seed=42)
    res = sim.run(ticker="DEMO", n_steps=10)
    assert res.ticker == "DEMO"
    assert res.n_steps == 10
    assert len(res.price_path) == 11
