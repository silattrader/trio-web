"""Backtester tests — pure deterministic fixtures, no real network."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from trio_backtester import BacktestRequest, run_backtest, run_walk_forward
from trio_backtester.walk_forward import _split_indices, _stdev, _median
from trio_data_providers import EdgarPitProvider, MockPitProvider
from trio_backtester.metrics import (
    cagr,
    daily_returns,
    max_drawdown,
    sharpe,
    summarise,
    total_return,
)
from trio_backtester.strategies import sma, rba_snapshot

client = TestClient(app)


# ----------------------------- metrics -----------------------------------


def test_daily_returns_basic():
    assert daily_returns([100, 110, 99]) == [pytest.approx(0.10), pytest.approx(-0.10)]


def test_cagr_one_year_doubling():
    assert cagr([100, 200], n_days=252) == pytest.approx(1.0, rel=1e-3)


def test_max_drawdown_v_shape():
    # 100 -> 50 (-50%) -> 200; drawdown = -50%.
    assert max_drawdown([100, 80, 50, 100, 200]) == pytest.approx(-0.5, rel=1e-3)


def test_max_drawdown_monotone_up_is_zero():
    assert max_drawdown([100, 110, 120]) == 0.0


def test_sharpe_zero_vol_returns_zero():
    assert sharpe([0.001] * 30) == 0.0


def test_total_return_simple():
    assert total_return([100, 150]) == pytest.approx(0.5)


def test_summarise_returns_all_keys():
    out = summarise([100, 110, 105, 120], n_days=3, trade_returns=[0.1, -0.05, 0.15])
    assert set(out.keys()) == {
        "cagr", "sharpe", "max_drawdown", "total_return", "n_trades", "win_rate",
    }
    assert out["n_trades"] == 3
    assert out["win_rate"] == pytest.approx(2 / 3)


# ----------------------------- SMA strategy -------------------------------


def _trending_history(start: date, n: int, ticker: str = "AAA") -> tuple[list[date], dict]:
    dates = [start + timedelta(days=i) for i in range(n)]
    # Steady uptrend: 100 → 200 over n bars.
    prices = [100.0 * (1 + 0.005) ** i for i in range(n)]
    return dates, {ticker: dict(zip(dates, prices))}


def test_sma_signal_no_lookahead_in_first_window():
    closes = list(range(50))
    sig = sma.signal_series(closes, fast=10, slow=20)
    # Until index 19 we don't have a slow SMA → must be False.
    assert all(s is False for s in sig[:19])


def test_sma_uptrend_makes_money():
    dates, hist = _trending_history(date(2020, 1, 1), 260)
    equity, trades = sma.simulate(
        dates=dates, history=hist, fast=10, slow=30,
        initial_capital=100_000, fee_bps=0,
    )
    assert equity[-1] > equity[0]
    # Should have stayed long once fast crossed above slow.
    assert len(equity) == len(dates)


def test_sma_flat_market_breaks_even_minus_fees():
    dates = [date(2020, 1, 1) + timedelta(days=i) for i in range(100)]
    hist = {"AAA": {d: 100.0 for d in dates}}
    equity, _ = sma.simulate(dates, hist, fast=5, slow=20, initial_capital=10_000, fee_bps=0)
    # Flat prices → no whipsaw drift, equity stays put.
    assert equity[-1] == pytest.approx(equity[0], rel=1e-6)


# ----------------------------- RBA-snapshot ------------------------------


class _FakeStockResult:
    def __init__(self, ticker, score):
        self.ticker = ticker
        self.final_score = score


class _FakeScoreResp:
    def __init__(self, results):
        self.results = results


def test_rba_select_top_n_descending():
    resp = _FakeScoreResp([
        _FakeStockResult("LOW", 1.5),
        _FakeStockResult("HIGH", 4.5),
        _FakeStockResult("MID", 3.0),
        _FakeStockResult("UNSCORED", None),
    ])
    picked = rba_snapshot.select_top_n(resp, top_n=2, available={"LOW", "HIGH", "MID"})
    assert picked == ["HIGH", "MID"]


def test_rba_simulate_equal_weight_buy_and_hold():
    dates, hist = _trending_history(date(2021, 1, 1), 60, ticker="AAA")
    # Add a flat ticker to test equal-weighting.
    hist["BBB"] = {d: 100.0 for d in dates}
    equity, trades = rba_snapshot.simulate(
        dates=dates, history=hist, selected=["AAA", "BBB"],
        rebalance_days=21, initial_capital=10_000, fee_bps=0,
    )
    assert len(equity) == len(dates)
    # AAA up, BBB flat → equal-weight portfolio is up but less than AAA alone.
    aaa_only = hist["AAA"][dates[-1]] / hist["AAA"][dates[0]]
    assert 1.0 < equity[-1] / equity[0] < aaa_only
    # Two trades — one per ticker.
    assert len(trades) == 2


# ----------------------------- engine integration ------------------------


def test_engine_sma_end_to_end():
    dates, hist = _trending_history(date(2020, 1, 1), 260)
    req = BacktestRequest(
        tickers=["AAA"], start=dates[0], end=dates[-1],
        fast=10, slow=30, fee_bps=0,
    )
    resp = run_backtest(req, "sma", history=hist, dates=dates)
    assert resp.strategy == "sma"
    assert len(resp.equity_curve) == len(dates)
    assert resp.metrics.total_return > 0
    assert resp.benchmark_metrics is not None
    # No lookahead warnings on the SMA path.
    assert resp.warnings == []


def test_engine_rba_snapshot_warns_about_lookahead():
    dates, hist = _trending_history(date(2020, 1, 1), 60, ticker="AAA")
    hist["BBB"] = {d: 100.0 for d in dates}
    req = BacktestRequest(
        tickers=["AAA", "BBB"], start=dates[0], end=dates[-1], top_n=2, fee_bps=0,
    )
    fake_resp = _FakeScoreResp([
        _FakeStockResult("AAA", 4.0),
        _FakeStockResult("BBB", 3.0),
    ])
    resp = run_backtest(
        req, "rba_snapshot", history=hist, dates=dates,
        score_fn=lambda *args, **kw: fake_resp,
    )
    assert any("lookahead" in w.lower() for w in resp.warnings)
    assert resp.metrics.total_return > 0


# ----------------------------- API endpoint ------------------------------


def test_backtest_endpoint_rejects_inverted_dates():
    body = client.post(
        "/backtest?strategy=sma",
        json={"tickers": ["AAPL"], "start": "2024-01-01", "end": "2023-01-01"},
    )
    assert body.status_code == 400


# ----------------------------- walk-forward ------------------------------


def test_split_indices_balanced():
    # 10 days into 4 windows → 3,3,2,2
    out = _split_indices(10, 4)
    sizes = [hi - lo for lo, hi in out]
    assert sizes == [3, 3, 2, 2]
    # Contiguous + covers full range.
    assert out[0][0] == 0 and out[-1][1] == 10


def test_split_indices_drops_too_small_windows():
    # 5 days into 4 → 2,1,1,1; only the first slice survives the >=2 filter.
    out = _split_indices(5, 4)
    assert all(hi - lo >= 2 for lo, hi in out)
    assert len(out) == 1


def test_median_and_stdev_helpers():
    assert _median([1.0, 2.0, 3.0]) == 2.0
    assert _median([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert _median([]) == 0.0
    assert _stdev([1.0]) == 0.0
    # 1, 2, 3 → mean 2, var = (1+0+1)/2 = 1
    assert _stdev([1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_walk_forward_sma_uptrend_aggregate():
    dates, hist = _trending_history(date(2020, 1, 1), 260)
    req = BacktestRequest(
        tickers=["AAA"], start=dates[0], end=dates[-1],
        fast=10, slow=30, fee_bps=0,
    )
    resp = run_walk_forward(
        req, "sma", n_windows=4, history=hist, dates=dates,
    )
    assert resp.aggregate.n_windows == 4
    assert len(resp.windows) == 4
    # Steady uptrend → every sub-window is positive once SMA arms.
    assert resp.aggregate.pct_windows_positive >= 0.5
    # Indices are 0..3 and dates are non-overlapping & ordered.
    assert [w.index for w in resp.windows] == [0, 1, 2, 3]
    for prev, curr in zip(resp.windows, resp.windows[1:]):
        assert prev.end < curr.start


def test_walk_forward_rejects_n_windows_lt_2():
    dates, hist = _trending_history(date(2020, 1, 1), 100)
    req = BacktestRequest(tickers=["AAA"], start=dates[0], end=dates[-1])
    with pytest.raises(ValueError):
        run_walk_forward(req, "sma", n_windows=1, history=hist, dates=dates)


# ----------------------------- Path 3 / rba_pit --------------------------


def test_mock_pit_provider_is_deterministic():
    p = MockPitProvider()
    a = p.fetch_as_of(["AAPL", "MSFT"], as_of=date(2022, 6, 1), model="bos")
    b = p.fetch_as_of(["AAPL", "MSFT"], as_of=date(2022, 6, 1), model="bos")
    assert a.rows == b.rows
    assert any("synthetic_pit" in w for w in a.warnings)


def test_mock_pit_provider_drifts_over_time():
    p = MockPitProvider()
    early = p.fetch_as_of(["AAPL"], as_of=date(2018, 1, 1), model="bos").rows[0]
    late = p.fetch_as_of(["AAPL"], as_of=date(2024, 1, 1), model="bos").rows[0]
    # Should NOT be identical — that's the whole point of PIT.
    assert early != late
    # But same ticker so the "anchor" base values overlap; only drift differs.
    assert early["ticker"] == late["ticker"] == "AAPL"


def test_edgar_pit_is_a_documented_stub():
    with pytest.raises(NotImplementedError):
        EdgarPitProvider().fetch_as_of(["AAPL"], as_of=date(2024, 1, 1), model="bos")


def test_engine_rba_pit_rebalances_per_window():
    """rba_pit calls score_fn at t=0 and again every rebalance_days bars."""
    dates, hist = _trending_history(date(2020, 1, 1), 100, ticker="AAA")
    hist["BBB"] = {d: 100.0 + i * 0.1 for i, d in enumerate(dates)}
    hist["CCC"] = {d: 200.0 - i * 0.05 for i, d in enumerate(dates)}

    call_dates: list[date] = []

    def fake_score_fn(tickers, model, as_of):
        call_dates.append(as_of)
        # Rotate the "winner" each call so selection actually changes.
        idx = len(call_dates) - 1
        scored = [_FakeStockResult(tickers[(idx + i) % len(tickers)], 4 - i) for i in range(len(tickers))]
        return _FakeScoreResp(scored)

    req = BacktestRequest(
        tickers=["AAA", "BBB", "CCC"], start=dates[0], end=dates[-1],
        top_n=2, rebalance_days=20, fee_bps=0,
    )
    resp = run_backtest(
        req, "rba_pit", history=hist, dates=dates, score_fn=fake_score_fn,
    )
    # Should have rebalanced multiple times (100 days / 20 ≈ 5).
    assert len(call_dates) >= 4
    # First call must use t=0; subsequent calls use later dates.
    assert call_dates[0] == dates[0]
    for prev, curr in zip(call_dates, call_dates[1:]):
        assert curr > prev
    assert any("rba_pit" in w.lower() or "rebalances" in w.lower() for w in resp.warnings)


def test_walk_forward_endpoint_sma_with_mocked_history(monkeypatch):
    dates, hist = _trending_history(date(2022, 1, 3), 260)
    monkeypatch.setattr("app.main.fetch_history", lambda t, s, e: (dates, hist))
    body = client.post(
        "/backtest/walk_forward?strategy=sma&n_windows=4",
        json={
            "tickers": ["AAA"], "start": "2022-01-03", "end": "2023-01-03",
            "fast": 10, "slow": 30, "fee_bps": 0,
        },
    ).json()
    assert body["aggregate"]["n_windows"] == 4
    assert len(body["windows"]) == 4
    assert "pct_windows_beating_benchmark" in body["aggregate"]


def test_backtest_endpoint_sma_with_mocked_history(monkeypatch):
    dates, hist = _trending_history(date(2022, 1, 3), 260)
    monkeypatch.setattr("app.main.fetch_history", lambda t, s, e: (dates, hist))
    body = client.post(
        "/backtest?strategy=sma",
        json={
            "tickers": ["AAA"], "start": "2022-01-03", "end": "2023-01-03",
            "fast": 10, "slow": 30, "fee_bps": 0,
        },
    ).json()
    assert body["strategy"] == "sma"
    assert len(body["equity_curve"]) == len(dates)
    assert body["metrics"]["total_return"] > 0
