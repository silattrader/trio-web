"""Curated universes module + /universes endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from trio_data_providers import (
    ALL_UNIVERSES,
    CURATED_DEMO,
    KLCI_30,
    SP500_TOP_100,
    Universe,
    get_universe,
)
from trio_data_providers.retail_pit import TICKER_TO_ARTICLE

client = TestClient(app)


# ---- module-level invariants --------------------------------------------


def test_all_universes_have_distinct_ids():
    ids = [u.id for u in ALL_UNIVERSES.values()]
    assert len(ids) == len(set(ids))


def test_curated_demo_unchanged():
    """28-name basket must NOT drift — it backs the documented MLA gate
    numbers in docs/algorithms/mla.md and the walk-forward results."""
    assert CURATED_DEMO.id == "curated_demo"
    assert len(CURATED_DEMO.tickers) == 28
    assert "AAPL" in CURATED_DEMO.tickers
    assert "JPM" not in CURATED_DEMO.tickers   # banks are excluded by design (Z' = None)


def test_sp500_top_100_is_us_coverage():
    assert SP500_TOP_100.coverage == "us"
    assert 50 < len(SP500_TOP_100.tickers) <= 150
    # No duplicates
    assert len(SP500_TOP_100.tickers) == len(set(SP500_TOP_100.tickers))


def test_klci_30_is_my_coverage():
    assert KLCI_30.coverage == "my"
    assert len(KLCI_30.tickers) == 30
    # Bloomberg-style "MK" suffix
    assert all(t.endswith(" MK") for t in KLCI_30.tickers)


def test_get_universe_known_ids():
    for uid in ("curated_demo", "sp500_top_100", "klci_30"):
        u = get_universe(uid)
        assert isinstance(u, Universe)
        assert u.id == uid


def test_get_universe_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        get_universe("nonexistent")


# ---- Wikipedia mapping coverage -----------------------------------------


def test_curated_demo_fully_mapped_for_retail_flow():
    """Every ticker in the documented demo universe must have a Wikipedia
    article so retail_flow works without warnings."""
    missing = [t for t in CURATED_DEMO.tickers if t not in TICKER_TO_ARTICLE]
    assert missing == [], f"missing Wikipedia mapping: {missing}"


def test_sp500_top_100_mostly_mapped():
    """SP500 top 100 may have a couple unmapped names; assert most are covered."""
    missing = [t for t in SP500_TOP_100.tickers if t not in TICKER_TO_ARTICLE]
    coverage = 1.0 - len(missing) / len(SP500_TOP_100.tickers)
    assert coverage >= 0.85, f"only {coverage:.0%} mapped; missing: {missing}"


def test_klci_30_partial_mapping_documented():
    """KLCI Wikipedia coverage is intentionally partial — 'documented as
    such' is the contract. Just assert SOMETHING is mapped, since the
    intent is we add to it over time."""
    mapped = [t for t in KLCI_30.tickers if t in TICKER_TO_ARTICLE]
    assert len(mapped) >= 10, f"only {len(mapped)} KLCI names mapped"


# ---- /universes endpoint -------------------------------------------------


def test_universes_endpoint_returns_all_three():
    body = client.get("/universes").json()
    ids = [u["id"] for u in body["universes"]]
    assert "curated_demo" in ids
    assert "sp500_top_100" in ids
    assert "klci_30" in ids


def test_universes_endpoint_carries_full_ticker_list():
    body = client.get("/universes").json()
    sp500 = next(u for u in body["universes"] if u["id"] == "sp500_top_100")
    assert sp500["n"] == len(sp500["tickers"])
    assert "MSFT" in sp500["tickers"]


def test_universes_endpoint_includes_metadata():
    body = client.get("/universes").json()
    klci = next(u for u in body["universes"] if u["id"] == "klci_30")
    assert klci["coverage"] == "my"
    assert klci["snapshot"]   # any non-empty ISO date
    assert klci["label"].startswith("FBM KLCI")
