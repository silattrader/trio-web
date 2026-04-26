"""EdgarPitProvider tests — fully mocked, no real network.

We monkey-patch the HTTP-fetching internals in ``_edgar_client`` so the
provider's logic (CIK lookup, latest_as_of filtering, Altman-Z' computation,
trailing dividend sum) can be verified deterministically.
"""
from __future__ import annotations

from datetime import date

import pytest

from trio_data_providers import EdgarPitProvider, _edgar_client as ec


# --- fixtures -------------------------------------------------------------


@pytest.fixture
def patched_edgar(monkeypatch, tmp_path):
    """Replace network + cache I/O with deterministic in-memory data."""
    monkeypatch.setattr(ec, "CACHE_DIR", tmp_path)

    ticker_map = {"AAPL": "0000320193", "MSFT": "0000789019"}

    def _fake_ticker_map(*, ttl_seconds=ec.DEFAULT_TTL_SECONDS):
        return dict(ticker_map)

    # Companyfacts blobs — covers a balance sheet that comfortably solves for
    # Altman Z' > 1.5 (so we exercise the math, not just the no-data path).
    def _aapl_facts():
        # (val, end, filed, form)
        def points(records, unit="USD"):
            return [
                {"val": v, "end": e, "filed": f, "form": form, "fy": 2022, "fp": "FY"}
                for v, e, f, form in records
            ]
        return {
            "cik": 320193,
            "entityName": "Apple Inc.",
            "facts": {
                "us-gaap": {
                    "Assets": {"units": {"USD": points([
                        (300_000, "2021-09-25", "2021-10-29", "10-K"),
                        (340_000, "2022-09-24", "2022-10-28", "10-K"),
                    ])}},
                    "Liabilities": {"units": {"USD": points([
                        (250_000, "2022-09-24", "2022-10-28", "10-K"),
                    ])}},
                    "AssetsCurrent": {"units": {"USD": points([
                        (130_000, "2022-09-24", "2022-10-28", "10-K"),
                    ])}},
                    "LiabilitiesCurrent": {"units": {"USD": points([
                        (100_000, "2022-09-24", "2022-10-28", "10-K"),
                    ])}},
                    "RetainedEarningsAccumulatedDeficit": {"units": {"USD": points([
                        (50_000, "2022-09-24", "2022-10-28", "10-K"),
                    ])}},
                    "OperatingIncomeLoss": {"units": {"USD": points([
                        (110_000, "2022-09-24", "2022-10-28", "10-K"),
                    ])}},
                    "Revenues": {"units": {"USD": points([
                        (380_000, "2022-09-24", "2022-10-28", "10-K"),
                    ])}},
                    "StockholdersEquity": {"units": {"USD": points([
                        (90_000, "2022-09-24", "2022-10-28", "10-K"),
                    ])}},
                    "CommonStockDividendsPerShareDeclared": {"units": {"USD/shares": [
                        {"val": 0.22, "end": "2021-12-25", "filed": "2022-01-28", "form": "10-Q", "fy": 2022, "fp": "Q1"},
                        {"val": 0.23, "end": "2022-03-26", "filed": "2022-04-29", "form": "10-Q", "fy": 2022, "fp": "Q2"},
                        {"val": 0.23, "end": "2022-06-25", "filed": "2022-07-29", "form": "10-Q", "fy": 2022, "fp": "Q3"},
                        # 10-K full-year row that should be FILTERED OUT to avoid double-counting.
                        {"val": 0.91, "end": "2022-09-24", "filed": "2022-10-28", "form": "10-K", "fy": 2022, "fp": "FY"},
                        {"val": 0.24, "end": "2022-12-31", "filed": "2023-02-03", "form": "10-Q", "fy": 2023, "fp": "Q1"},
                    ]}},
                },
                "dei": {
                    "EntityCommonStockSharesOutstanding": {"units": {"shares": [
                        {"val": 16_000_000, "end": "2022-10-15", "filed": "2022-10-28", "form": "10-K", "fy": 2022, "fp": "FY"},
                    ]}},
                },
            },
        }

    facts_by_cik = {"0000320193": _aapl_facts()}

    def _fake_companyfacts(cik, *, ttl_seconds=ec.DEFAULT_TTL_SECONDS):
        cik_padded = cik.zfill(10)
        if cik_padded not in facts_by_cik:
            raise ec.EdgarError(f"GET cik={cik_padded}: 404 not found")
        return facts_by_cik[cik_padded]

    monkeypatch.setattr(ec, "fetch_ticker_map", _fake_ticker_map)
    monkeypatch.setattr(ec, "fetch_companyfacts", _fake_companyfacts)
    return {"ticker_map": ticker_map, "facts_by_cik": facts_by_cik}


# --- low-level client tests ----------------------------------------------


def test_latest_as_of_picks_most_recent_visible_filing(patched_edgar):
    facts = patched_edgar["facts_by_cik"]["0000320193"]
    # As of 2022-01-01 only the 2021-09-25 figure has been filed.
    pt = ec.latest_as_of(
        facts, namespace="us-gaap", tag="Assets", unit="USD",
        as_of="2022-01-01", annual_only=True,
    )
    assert pt is not None
    assert pt.val == 300_000
    # As of 2023-01-01 the 2022-09-24 figure is now visible.
    pt2 = ec.latest_as_of(
        facts, namespace="us-gaap", tag="Assets", unit="USD",
        as_of="2023-01-01", annual_only=True,
    )
    assert pt2.val == 340_000


def test_latest_as_of_returns_none_when_nothing_filed_yet(patched_edgar):
    facts = patched_edgar["facts_by_cik"]["0000320193"]
    assert ec.latest_as_of(
        facts, namespace="us-gaap", tag="Assets", unit="USD",
        as_of="2020-01-01", annual_only=True,
    ) is None


def test_trailing_sum_excludes_unfiled_periods(patched_edgar):
    facts = patched_edgar["facts_by_cik"]["0000320193"]
    # As of 2022-12-01: Q1 (0.22) + Q2 (0.23) + Q3 (0.23) visible.
    # The 10-K FY=0.91 row must be filtered out (quarterly_only) so we don't
    # double-count. Q1 2023 (filed 2023-02-03) is not yet visible.
    total = ec.trailing_sum(
        facts, namespace="us-gaap",
        tag="CommonStockDividendsPerShareDeclared",
        unit="USD/shares", as_of="2022-12-01", days=365,
    )
    assert total == pytest.approx(0.22 + 0.23 + 0.23, abs=1e-9)


def test_trailing_sum_quarterly_filter_drops_10k_full_year(patched_edgar):
    """The 10-K FY entry would inflate the trailing sum if not filtered."""
    facts = patched_edgar["facts_by_cik"]["0000320193"]
    with_filter = ec.trailing_sum(
        facts, namespace="us-gaap",
        tag="CommonStockDividendsPerShareDeclared",
        unit="USD/shares", as_of="2023-01-01", days=365,
    )
    without_filter = ec.trailing_sum(
        facts, namespace="us-gaap",
        tag="CommonStockDividendsPerShareDeclared",
        unit="USD/shares", as_of="2023-01-01", days=365,
        quarterly_only=False,
    )
    assert with_filter is not None and without_filter is not None
    assert without_filter > with_filter


# --- provider integration -------------------------------------------------


def test_edgar_pit_returns_canonical_row(patched_edgar):
    p = EdgarPitProvider()
    res = p.fetch_as_of(["AAPL"], as_of=date(2023, 6, 1), model="bos")
    row = res.rows[0]
    assert row["ticker"] == "AAPL"
    assert row["name"] == "Apple Inc."
    assert row["altman_z"] is not None and row["altman_z"] > 1.5
    assert row["dvd_yld_ind"] is not None and row["dvd_yld_ind"] > 0
    # Forward-looking factors NOT recoverable from filings.
    assert row["vol_avg_3m"] is None
    assert row["target_return"] is None
    assert row["analyst_sent"] is None
    assert any("edgar_pit" in w for w in res.warnings)


def test_edgar_pit_handles_unknown_ticker(patched_edgar):
    p = EdgarPitProvider()
    res = p.fetch_as_of(["NOPE"], as_of=date(2023, 6, 1), model="bos")
    row = res.rows[0]
    assert row["altman_z"] is None
    assert row["_edgar_error"] == "cik_not_found"


def test_edgar_pit_no_lookahead_pre_filing(patched_edgar):
    """Before any 10-K is filed (2021-10-29), Altman-Z is unavailable."""
    p = EdgarPitProvider()
    res = p.fetch_as_of(["AAPL"], as_of=date(2020, 1, 1), model="bos")
    row = res.rows[0]
    assert row["altman_z"] is None
    assert row["dvd_yld_ind"] is None
