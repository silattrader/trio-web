"""Provider tests use mocks — no real network calls."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from trio_data_providers import ProviderError, get_provider, list_providers
from trio_data_providers.i3investor_provider import _parse_target_page, _sentiment


# ----------------------------- registry -----------------------------------


def test_registry_lists_all_providers():
    names = {p["name"] for p in list_providers()}
    assert names == {"yfinance", "tradingview", "i3investor", "bloomberg"}


def test_unknown_provider_raises():
    with pytest.raises(ProviderError):
        get_provider("does_not_exist")


# ----------------------------- bloomberg stub -----------------------------


def test_bloomberg_stub_requires_env(monkeypatch):
    for k in ("TRIO_BLOOMBERG_HOST", "TRIO_BLOOMBERG_PORT"):
        monkeypatch.delenv(k, raising=False)
    p = get_provider("bloomberg")
    with pytest.raises(ProviderError, match="not configured"):
        p.fetch(["AAPL US"], model="bos")


def test_bloomberg_with_env_still_stubbed(monkeypatch):
    monkeypatch.setenv("TRIO_BLOOMBERG_HOST", "localhost")
    monkeypatch.setenv("TRIO_BLOOMBERG_PORT", "8194")
    p = get_provider("bloomberg")
    with pytest.raises(ProviderError, match="stub"):
        p.fetch(["AAPL US"], model="bos")


def test_bloomberg_coverage_advertises_full_bos():
    cov = get_provider("bloomberg").coverage("bos")
    assert "altman_z" in cov and "vol_avg_3m" in cov


# ----------------------------- i3investor ----------------------------------


def test_i3_sentiment_buckets():
    assert _sentiment(buy=10, hold=0, sell=0) == 5.0
    assert _sentiment(buy=0, hold=0, sell=10) == 1.0
    assert _sentiment(buy=5, hold=5, sell=0) == 3.0
    assert _sentiment(0, 0, 0) is None


def test_i3_parses_minimal_page():
    html = """
    <h5 id='stock-heading'><strong>MAYBANK</strong></h5>
    <div id='stock-price-info'><strong>9.50</strong><strong>+0.10 (1.07%)</strong></div>
    <div class='col-sm-3 col-6'><strong>n/a</strong></div>
    <div class='col-sm-3 col-6'><strong>11.00</strong></div>
    <div class='col-4'><strong>2</strong></div>
    <div class='col-4'><strong>3</strong></div>
    <div class='col-4'><strong>10</strong></div>
    """
    out = _parse_target_page(html, "1155")
    assert out["name"] == "MAYBANK"
    assert out["px_last"] == 9.50
    assert out["best_target_price"] == 11.00
    assert out["target_return"] == pytest.approx(15.79, rel=1e-2)
    # 10 buy / 15 total -> 1 + 4*(10/15) ~= 3.67
    assert out["analyst_sent"] == pytest.approx(3.67, rel=1e-2)


def test_i3_fetch_uses_requests(monkeypatch):
    monkeypatch.setenv("TRIO_I3_RATE_LIMIT", "0")
    fake = MagicMock()
    fake.text = "<html></html>"
    fake.raise_for_status.return_value = None
    with patch("requests.get", return_value=fake) as g:
        p = get_provider("i3investor")
        result = p.fetch(["1155", "1023"], model="bos")
    assert g.call_count == 2
    assert result.provider == "i3investor"
    assert result.universe == "KLCI"
    assert any("partial" in w.lower() or "i3investor" in w.lower() for w in result.warnings)


# ----------------------------- yfinance -----------------------------------


def test_yfinance_coverage_includes_altman():
    assert "altman_z" in get_provider("yfinance").coverage("bos")


def test_yfinance_fetch_with_mocked_ticker():
    """End-to-end fetch with yfinance.Ticker fully mocked."""
    import pandas as pd

    fake_info = {
        "longName": "Apple Inc.",
        "currentPrice": 170.0,
        "targetMeanPrice": 200.0,
        "dividendYield": 0.0055,             # 0.55% as a fraction
        "recommendationMean": 1.8,           # yf scale: low=bullish
        "ebitda": 130_000_000_000,
        "totalRevenue": 380_000_000_000,
        "marketCap": 2_700_000_000_000,
        "trailingPE": 28.4,
        "sharesOutstanding": 15_700_000_000,
    }
    bs_data = {
        "2024-09-30": {
            "Total Assets": 365_000_000_000,
            "Total Liabilities Net Minority Interest": 290_000_000_000,
            "Current Assets": 145_000_000_000,
            "Current Liabilities": 120_000_000_000,
            "Retained Earnings": 8_000_000_000,
            "Cash And Cash Equivalents": 60_000_000_000,
            "Receivables": 30_000_000_000,
            "Inventory": 7_000_000_000,
            "Other Current Assets": 14_000_000_000,
            "Accounts Payable": 50_000_000_000,
            "Other Current Liabilities": 35_000_000_000,
            "Current Debt": 15_000_000_000,
            "Total Non Current Liabilities Net Minority Interest": 145_000_000_000,
        }
    }
    fake_bs = pd.DataFrame(bs_data)
    fake_hist = pd.DataFrame({"Volume": [100_000_000, 110_000_000, 90_000_000]})

    fake_ticker = MagicMock()
    fake_ticker.info = fake_info
    fake_ticker.history.return_value = fake_hist
    fake_ticker.balance_sheet = fake_bs

    with patch("yfinance.Ticker", return_value=fake_ticker):
        p = get_provider("yfinance")
        result = p.fetch(["AAPL"], model="bos")

    row = result.rows[0]
    assert row["ticker"] == "AAPL"
    assert row["name"] == "Apple Inc."
    assert row["vol_avg_3m"] == pytest.approx(100_000_000, rel=1e-3)
    assert row["target_return"] == pytest.approx(((200 - 170) / 170) * 100, rel=1e-3)
    assert row["dvd_yld_ind"] == pytest.approx(0.55, rel=1e-3)
    # 6 - 1.8 = 4.2 (BOS BUY threshold)
    assert row["analyst_sent"] == pytest.approx(4.2, rel=1e-3)
    assert isinstance(row["altman_z"], float)
    # MOS balance-sheet fields populated
    assert row["cash_near_cash"] == 60_000_000_000
    assert row["accounts_receivable"] == 30_000_000_000


# ----------------------------- tradingview --------------------------------


def test_tv_detect_market():
    from trio_data_providers.tradingview_provider import _detect_market

    assert _detect_market(["NASDAQ:AAPL"]) == "america"
    assert _detect_market(["NYSE:JPM"]) == "america"
    assert _detect_market(["MYX:1155"]) == "malaysia"
    assert _detect_market(["BURSA:1155"]) == "malaysia"
    assert _detect_market(["AAPL"]) == "america"


def test_tv_normalize_tickers():
    from trio_data_providers.tradingview_provider import _normalize_tickers

    assert _normalize_tickers(["AAPL", "MSFT"], "america") == [
        "NASDAQ:AAPL",
        "NASDAQ:MSFT",
    ]
    assert _normalize_tickers(["1155"], "malaysia") == ["MYX:1155"]
    assert _normalize_tickers(["NYSE:JPM"], "america") == ["NYSE:JPM"]


def test_tv_analyst_sent_from_rec_mark():
    from trio_data_providers.tradingview_provider import _analyst_sent_from_rec_mark

    assert _analyst_sent_from_rec_mark(1.0) == 5.0
    assert _analyst_sent_from_rec_mark(0.0) == 3.0
    assert _analyst_sent_from_rec_mark(-1.0) == 1.0
    assert _analyst_sent_from_rec_mark(None) is None


def test_tv_fetch_with_mocked_scanner():
    fake_payload = {
        "data": [
            {
                "s": "NASDAQ:AAPL",
                "d": [
                    "AAPL",                # name
                    "Apple Inc.",          # description
                    170.0,                 # close
                    100_000_000,           # average_volume_90d_calc
                    200.0,                 # price_target_average
                    0.55,                  # dividend_yield_recent
                    0.6,                   # Recommend.All
                    15_700_000_000,        # total_shares_outstanding
                ],
            }
        ]
    }
    fake_resp = MagicMock()
    fake_resp.json.return_value = fake_payload
    fake_resp.raise_for_status.return_value = None

    with patch("requests.post", return_value=fake_resp) as post:
        p = get_provider("tradingview")
        result = p.fetch(["AAPL"], model="bos")

    assert post.call_count == 1
    row = result.rows[0]
    assert row["ticker"] == "AAPL"
    assert row["name"] == "Apple Inc."
    assert row["vol_avg_3m"] == 100_000_000
    assert row["dvd_yld_ind"] == 0.55
    assert "altman_z" not in row
    assert row["target_return"] == pytest.approx(((200 - 170) / 170) * 100, rel=1e-3)
    assert row["px_last"] == 170.0
    assert row["best_target_price"] == 200.0
    # rec_mark 0.6 -> 1 + (0.6+1)/2 * 4 = 4.2
    assert row["analyst_sent"] == pytest.approx(4.2, rel=1e-3)
    assert any("unofficial" in w.lower() for w in result.warnings)


def test_tv_registered():
    p = get_provider("tradingview")
    assert p.name == "tradingview"
    cov = p.coverage("bos")
    assert "vol_avg_3m" in cov and "analyst_sent" in cov
    assert "altman_z" not in cov
