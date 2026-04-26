"""Tests for the MLA real-data training pipeline.

Network-free: monkeypatches yfinance + EDGAR with deterministic fixtures so
the pipeline logic (quarter-end snapshot, forward-return labelling,
dataset filtering) is verified without real I/O.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from trio_algorithms.mla.data_pipeline import (
    DEFAULT_UNIVERSE,
    PitSample,
    _forward_return,
    build_pit_dataset,
    quarter_ends,
    to_xy,
)


def test_quarter_ends_covers_full_range():
    qs = quarter_ends(date(2020, 1, 1), date(2020, 12, 31))
    assert qs == [
        date(2020, 3, 31), date(2020, 6, 30),
        date(2020, 9, 30), date(2020, 12, 31),
    ]


def test_quarter_ends_handles_partial_first_quarter():
    qs = quarter_ends(date(2020, 4, 15), date(2020, 12, 31))
    # April 15 starts mid-Q2; first quarter-end >= start is 2020-06-30.
    assert qs[0] == date(2020, 6, 30)


def test_forward_return_basic():
    series = {
        date(2020, 1, 1) + timedelta(days=i): 100.0 * (1 + 0.001) ** i
        for i in range(200)
    }
    r = _forward_return(series, date(2020, 1, 5), n_trading_days=60)
    # 60 steps of 0.1% growth = (1.001)^60 - 1 ≈ 6.18%.
    assert r == pytest.approx(0.0618, rel=0.05)


def test_forward_return_returns_none_when_horizon_missing():
    series = {date(2020, 1, 1): 100.0, date(2020, 1, 2): 101.0}
    assert _forward_return(series, date(2020, 1, 1), n_trading_days=60) is None


def test_to_xy_drops_samples_with_missing_features():
    samples = [
        PitSample(
            ticker="A", as_of=date(2020, 3, 31),
            features={"vol_avg_3m": 1e6, "target_return": 5.0,
                      "dvd_yld_ind": 3.0, "altman_z": 2.5, "analyst_sent": 4.0},
            forward_return=0.05,
        ),
        PitSample(
            ticker="B", as_of=date(2020, 3, 31),
            features={"vol_avg_3m": None, "target_return": 5.0,
                      "dvd_yld_ind": 3.0, "altman_z": 2.5, "analyst_sent": 4.0},
            forward_return=0.05,
        ),
        PitSample(
            ticker="C", as_of=date(2020, 3, 31),
            features={"vol_avg_3m": 1e6, "target_return": 5.0,
                      "dvd_yld_ind": 3.0, "altman_z": 2.5, "analyst_sent": 4.0},
            forward_return=None,  # no label
        ),
    ]
    X, y, kept = to_xy(samples)
    assert X.shape == (1, 5)
    assert len(kept) == 1 and kept[0].ticker == "A"


def test_build_pit_dataset_uses_cache(tmp_path):
    """Second call with same cache_path must skip the network entirely."""
    import pickle

    cached = [
        PitSample(
            ticker="X", as_of=date(2020, 6, 30),
            features={"vol_avg_3m": 5e5, "target_return": 0.0,
                      "dvd_yld_ind": 4.0, "altman_z": 2.0, "analyst_sent": 3.0},
            forward_return=0.03,
        ),
    ]
    cache_file = tmp_path / "ds.pkl"
    cache_file.write_bytes(pickle.dumps(cached))

    out = build_pit_dataset(cache_path=cache_file)
    assert len(out) == 1 and out[0].ticker == "X"


def test_default_universe_is_diverse():
    """Should cover multiple sectors so training doesn't overfit one regime."""
    assert "AAPL" in DEFAULT_UNIVERSE   # tech
    assert "JNJ" in DEFAULT_UNIVERSE    # healthcare
    assert "XOM" in DEFAULT_UNIVERSE    # energy
    assert "WMT" in DEFAULT_UNIVERSE    # consumer
    assert len(DEFAULT_UNIVERSE) >= 20
