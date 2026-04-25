from unittest.mock import MagicMock, patch

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_providers_list():
    body = client.get("/providers").json()
    names = [p["name"] for p in body["providers"]]
    assert names == ["yfinance", "tradingview", "i3investor", "bloomberg"]


def test_universe_yfinance_endpoint(monkeypatch):
    fake_ticker = MagicMock()
    fake_ticker.info = {
        "longName": "Apple", "currentPrice": 170, "targetMeanPrice": 200,
        "dividendYield": 0.005, "recommendationMean": 2.0,
        "ebitda": 1, "totalRevenue": 1, "marketCap": 1, "sharesOutstanding": 1, "trailingPE": 28,
    }
    fake_ticker.history.return_value = pd.DataFrame({"Volume": [100, 200, 300]})
    fake_ticker.balance_sheet = pd.DataFrame()
    with patch("yfinance.Ticker", return_value=fake_ticker):
        r = client.post(
            "/universe/yfinance?model=bos",
            json={"tickers": ["AAPL"]},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "yfinance"
    assert body["universe"] == "SP500"
    assert body["rows"][0]["ticker"] == "AAPL"
    assert "altman_z" in body["coverage"]


def test_universe_bloomberg_returns_502_when_unconfigured(monkeypatch):
    for k in ("TRIO_BLOOMBERG_HOST", "TRIO_BLOOMBERG_PORT"):
        monkeypatch.delenv(k, raising=False)
    r = client.post("/universe/bloomberg?model=bos", json={"tickers": ["AAPL US"]})
    assert r.status_code == 502
    assert "not configured" in r.json()["detail"]


def test_universe_unknown_provider_returns_502():
    r = client.post("/universe/quantum_woo?model=bos", json={"tickers": ["X"]})
    assert r.status_code == 502
