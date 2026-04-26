"""RetailFlowPitProvider + Wikipedia client tests — fully mocked HTTP."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from trio_data_providers import RetailFlowPitProvider
from trio_data_providers import _wikipedia_client as wc
from trio_data_providers.retail_pit import (
    TICKER_TO_ARTICLE,
    _attention_z,
    score_from_attention_z,
)


# ---- score mapping ------------------------------------------------------


def test_score_from_attention_z_thresholds():
    assert score_from_attention_z(3.0) == 1.0     # extreme spike
    assert score_from_attention_z(2.0) == 1.0     # boundary
    assert score_from_attention_z(1.5) == 2.0     # elevated
    assert score_from_attention_z(1.0) == 2.0     # boundary
    assert score_from_attention_z(0.0) == 3.0     # neutral
    assert score_from_attention_z(-2.0) == 3.0    # below baseline still neutral
    assert score_from_attention_z(None) is None


def test_attention_z_basic():
    """Steady baseline + recent spike → positive z-score."""
    base = date(2023, 6, 1)
    series: dict[date, int] = {}
    # 365 days of baseline = 1000 ± 100 (uniform 800-1200, mean 1000, std ~115)
    for i in range(365):
        d = base - timedelta(days=365 - i)
        # Deterministic sawtooth around 1000.
        series[d] = 900 + (i % 4) * 50  # values 900, 950, 1000, 1050
    # Recent 30 days = clear spike (3000 each)
    for i in range(30):
        d = base - timedelta(days=29 - i)
        series[d] = 3000
    stats = _attention_z(series, as_of=base, recent_days=30, baseline_days=365)
    assert stats.z_score is not None and stats.z_score > 5  # huge spike


def test_attention_z_returns_none_when_no_baseline():
    """Less than 30 baseline days → z_score = None (insufficient signal)."""
    base = date(2023, 6, 1)
    series = {base - timedelta(days=i): 100 for i in range(15)}  # only 15 days
    stats = _attention_z(series, as_of=base, recent_days=30, baseline_days=365)
    assert stats.z_score is None


def test_attention_z_returns_none_when_zero_variance():
    base = date(2023, 6, 1)
    # Flat 1000 for 365 days, no recent change.
    series = {base - timedelta(days=i): 1000 for i in range(365)}
    stats = _attention_z(series, as_of=base, recent_days=30, baseline_days=365)
    # Std is 0 → can't compute z; provider treats this as missing.
    assert stats.z_score is None


# ---- provider with mocked HTTP ------------------------------------------


@pytest.fixture
def patched_wiki(monkeypatch):
    """Stub fetch_pageviews_window to return controlled series."""

    def make_series(*, baseline: int, recent: int, as_of: date) -> dict[date, int]:
        s: dict[date, int] = {}
        # 12 months of baseline with light noise so std > 0.
        for i in range(335):
            d = as_of - timedelta(days=365 - i)
            # Sawtooth around `baseline` to give nonzero variance.
            s[d] = baseline + ((i % 5) - 2) * max(1, baseline // 20)
        # Recent 30 days at `recent`.
        for i in range(30):
            d = as_of - timedelta(days=29 - i)
            s[d] = recent
        return s

    db = {
        # AAPL: hot — recent ~3× baseline → big positive z
        "Apple_Inc.": make_series(baseline=2000, recent=6500, as_of=date(2023, 6, 1)),
        # MSFT: quiet — recent ~baseline → z near 0
        "Microsoft": make_series(baseline=1500, recent=1500, as_of=date(2023, 6, 1)),
    }

    def fake_fetch(article, *, as_of, lookback_days=365, ttl_seconds=None):
        return dict(db.get(article, {}))

    monkeypatch.setattr(wc, "fetch_pageviews_window", fake_fetch)
    return db


def test_retail_flow_detects_attention_spike(patched_wiki):
    p = RetailFlowPitProvider(recent_days=30, baseline_days=365)
    res = p.fetch_as_of(["AAPL", "MSFT"], as_of=date(2023, 6, 1), model="bos")
    aapl = next(r for r in res.rows if r["ticker"] == "AAPL")
    msft = next(r for r in res.rows if r["ticker"] == "MSFT")
    # AAPL spike → low score (contrarian SELL).
    assert aapl["retail_flow"] in (1.0, 2.0)
    assert aapl["_retail_attention_z"] > 1.0
    # MSFT flat → neutral.
    assert msft["retail_flow"] == 3.0
    assert abs(msft["_retail_attention_z"]) < 1.0


def test_retail_flow_unknown_ticker_returns_none(patched_wiki):
    p = RetailFlowPitProvider()
    res = p.fetch_as_of(["NOTREAL"], as_of=date(2023, 6, 1), model="bos")
    assert res.rows[0]["retail_flow"] is None
    assert any("no Wikipedia article mapped" in w for w in res.warnings)


def test_retail_flow_handles_no_pageviews_data(patched_wiki, monkeypatch):
    """Article exists in mapping but pageview API returned nothing."""
    monkeypatch.setattr(wc, "fetch_pageviews_window", lambda *a, **kw: {})
    p = RetailFlowPitProvider()
    res = p.fetch_as_of(["AAPL"], as_of=date(2023, 6, 1), model="bos")
    assert res.rows[0]["retail_flow"] is None


def test_default_universe_has_wiki_mappings():
    """Every ticker in the curated MLA training universe must have a
    Wikipedia article — otherwise retail_flow drops to None for them."""
    from trio_algorithms.mla.data_pipeline import DEFAULT_UNIVERSE
    for t in DEFAULT_UNIVERSE:
        assert t in TICKER_TO_ARTICLE, f"missing Wikipedia mapping for {t}"


def test_custom_mapping_overrides_default():
    custom = {"FOO": "Some_Test_Article"}
    p = RetailFlowPitProvider(ticker_to_article=custom)
    # Default universe ticker shouldn't resolve under a custom-only map.
    assert "AAPL" not in p._map
    assert p._map["FOO"] == "Some_Test_Article"
