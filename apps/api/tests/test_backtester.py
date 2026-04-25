"""Backtester tests — pure deterministic fixtures, no real network."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from trio_backtester import BacktestRequest, run_backtest
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
