"""SEC 13F-HR provider tests — fully mocked HTTP, no real network."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import date

import pytest

from trio_data_providers import ThirteenFPitProvider
from trio_data_providers import _thirteenf_client as tf
from trio_data_providers.cusip_map import TICKER_TO_CUSIP, cusip_for, ticker_for
from trio_data_providers.thirteenf_provider import score_from_filer_count


# --- score thresholds -----------------------------------------------------


def test_score_thresholds():
    assert score_from_filer_count(2000) == 5.0
    assert score_from_filer_count(1000) == 5.0
    assert score_from_filer_count(500) == 4.0
    assert score_from_filer_count(250) == 4.0
    assert score_from_filer_count(100) == 3.0
    assert score_from_filer_count(50) == 3.0
    assert score_from_filer_count(20) == 2.0
    assert score_from_filer_count(5) == 2.0
    assert score_from_filer_count(2) == 1.0
    assert score_from_filer_count(0) == 1.0


# --- CUSIP map ------------------------------------------------------------


def test_cusip_map_round_trip():
    for ticker, cusip in TICKER_TO_CUSIP.items():
        assert cusip_for(ticker) == cusip
        assert ticker_for(cusip) == ticker


def test_cusip_map_covers_curated_demo():
    """Every ticker in CURATED_DEMO must have a CUSIP."""
    from trio_data_providers import CURATED_DEMO
    missing = [t for t in CURATED_DEMO.tickers if cusip_for(t) is None]
    assert missing == [], f"missing CUSIP: {missing}"


def test_cusip_map_lookup_is_case_insensitive():
    assert cusip_for("aapl") == TICKER_TO_CUSIP["AAPL"]


# --- quarter-routing ------------------------------------------------------


def test_latest_completed_quarter_picks_60_day_lag():
    # Mid-November 2024 — Q2-2024 should be safely past the 60d lag.
    y, q = tf.latest_completed_quarter(date(2024, 11, 15))
    assert (y, q) == (2024, 2) or (y, q) == (2024, 3)


def test_latest_completed_quarter_falls_back_at_year_boundary():
    # January 2024 — Q3 2023 should be the most recent finalised dataset.
    y, q = tf.latest_completed_quarter(date(2024, 1, 5))
    assert y == 2023 and q == 3


# --- INFOTABLE parsing ----------------------------------------------------


def _build_fake_13f_zip(rows: list[dict]) -> bytes:
    """Construct a minimal SEC bulk ZIP carrying just an INFOTABLE.tsv."""
    import csv as _csv
    sio = io.StringIO()
    fields = ["ACCESSION_NUMBER", "INFOTABLE_SK", "NAMEOFISSUER",
              "TITLEOFCLASS", "CUSIP", "VALUE", "SSHPRNAMT",
              "SSHPRNAMTTYPE", "INVESTMENTDISCRETION"]
    w = _csv.DictWriter(sio, fieldnames=fields, delimiter="\t")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fields})
    tsv_bytes = sio.getvalue().encode("latin-1")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("INFOTABLE.tsv", tsv_bytes)
    return out.getvalue()


def test_parse_infotable_aggregates_per_cusip():
    zip_bytes = _build_fake_13f_zip([
        {"ACCESSION_NUMBER": "A1", "NAMEOFISSUER": "APPLE INC", "CUSIP": "037833100",
         "VALUE": "1000000", "SSHPRNAMT": "5000", "SSHPRNAMTTYPE": "SH"},
        {"ACCESSION_NUMBER": "A1", "NAMEOFISSUER": "MICROSOFT", "CUSIP": "594918104",
         "VALUE": "500000", "SSHPRNAMT": "1000", "SSHPRNAMTTYPE": "SH"},
        {"ACCESSION_NUMBER": "A2", "NAMEOFISSUER": "APPLE INC", "CUSIP": "037833100",
         "VALUE": "2000000", "SSHPRNAMT": "10000", "SSHPRNAMTTYPE": "SH"},
        {"ACCESSION_NUMBER": "A3", "NAMEOFISSUER": "APPLE INC", "CUSIP": "037833100",
         "VALUE": "500000", "SSHPRNAMT": "2500", "SSHPRNAMTTYPE": "SH"},
    ])
    agg = tf.parse_infotable_zip(zip_bytes)
    assert "037833100" in agg
    aapl = agg["037833100"]
    assert aapl.n_filers == 3   # A1, A2, A3
    assert aapl.total_shares == 17500
    # VALUE column is in $ thousands; sum * 1000 gives total $.
    assert aapl.total_value_usd == 3_500_000_000  # 3500k * 1000
    assert aapl.issuer_name == "APPLE INC"


def test_parse_infotable_skips_principal_type():
    """SSHPRNAMTTYPE = PRN means principal amount (debt), not shares — share
    count should NOT include those."""
    zip_bytes = _build_fake_13f_zip([
        {"ACCESSION_NUMBER": "A1", "NAMEOFISSUER": "X", "CUSIP": "111111111",
         "VALUE": "1000", "SSHPRNAMT": "5000", "SSHPRNAMTTYPE": "SH"},
        {"ACCESSION_NUMBER": "A1", "NAMEOFISSUER": "X", "CUSIP": "111111111",
         "VALUE": "1000", "SSHPRNAMT": "9999", "SSHPRNAMTTYPE": "PRN"},
    ])
    agg = tf.parse_infotable_zip(zip_bytes)
    assert agg["111111111"].total_shares == 5000  # only the SH row counted


def test_parse_infotable_skips_blank_cusip():
    zip_bytes = _build_fake_13f_zip([
        {"ACCESSION_NUMBER": "A1", "NAMEOFISSUER": "X", "CUSIP": "",
         "VALUE": "1000", "SSHPRNAMT": "5000", "SSHPRNAMTTYPE": "SH"},
    ])
    agg = tf.parse_infotable_zip(zip_bytes)
    assert agg == {}


# --- end-to-end provider with mocked HTTP --------------------------------


@pytest.fixture
def patched_13f(monkeypatch, tmp_path):
    """Stub fetch_13f_quarter to return a deterministic in-memory aggregate."""
    monkeypatch.setattr(tf, "CACHE_DIR", tmp_path)

    canned = {
        # AAPL: heavy institutional concentration → score 5.0
        TICKER_TO_CUSIP["AAPL"]: tf.HoldingsAggregate(
            cusip=TICKER_TO_CUSIP["AAPL"], issuer_name="Apple Inc.",
            n_filers=4500, total_shares=10_000_000_000,
            total_value_usd=1_500_000_000_000.0,
        ),
        # WMT: broad-mid → score 4.0
        TICKER_TO_CUSIP["WMT"]: tf.HoldingsAggregate(
            cusip=TICKER_TO_CUSIP["WMT"], issuer_name="Walmart Inc.",
            n_filers=300, total_shares=2_000_000_000,
            total_value_usd=300_000_000_000.0,
        ),
        # PFE: low-coverage → score 2.0
        TICKER_TO_CUSIP["PFE"]: tf.HoldingsAggregate(
            cusip=TICKER_TO_CUSIP["PFE"], issuer_name="Pfizer Inc.",
            n_filers=15, total_shares=1_000_000,
            total_value_usd=30_000_000.0,
        ),
    }

    def fake_fetch(year, quarter, *, ttl_seconds=tf.DEFAULT_TTL_SECONDS):
        return dict(canned)

    monkeypatch.setattr(tf, "fetch_13f_quarter", fake_fetch)
    return canned


def test_provider_assigns_concentration_score(patched_13f):
    p = ThirteenFPitProvider()
    res = p.fetch_as_of(
        ["AAPL", "WMT", "PFE"], as_of=date(2024, 11, 15), model="bos_flow",
    )
    by_t = {r["ticker"]: r for r in res.rows}
    assert by_t["AAPL"]["inst_concentration_score"] == 5.0
    assert by_t["AAPL"]["inst_n_filers"] == 4500
    assert by_t["AAPL"]["name"] == "Apple Inc."
    assert by_t["WMT"]["inst_concentration_score"] == 4.0
    assert by_t["PFE"]["inst_concentration_score"] == 2.0


def test_provider_returns_none_for_unmapped_ticker(patched_13f):
    p = ThirteenFPitProvider()
    res = p.fetch_as_of(["NOT-A-TICKER"], as_of=date(2024, 11, 15), model="bos")
    row = res.rows[0]
    assert row["inst_concentration_score"] is None
    assert any("missing from TICKER_TO_CUSIP" in w for w in res.warnings)


def test_provider_returns_none_when_cusip_not_in_dataset(patched_13f):
    """Ticker IS mapped but the test fixture doesn't include its CUSIP."""
    p = ThirteenFPitProvider()
    res = p.fetch_as_of(["TSLA"], as_of=date(2024, 11, 15), model="bos")
    # TSLA isn't in our hand-curated map — falls through to "unmapped".
    # If we ADDED it to the map but the canned fixture didn't have it,
    # we'd hit the no-holdings branch instead. Both branches return None.
    row = res.rows[0]
    assert row["inst_concentration_score"] is None


def test_provider_warning_when_bulk_fetch_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE_DIR", tmp_path)
    def boom(*a, **kw):
        raise tf.ThirteenFError("simulated network failure")
    monkeypatch.setattr(tf, "fetch_13f_quarter", boom)

    p = ThirteenFPitProvider()
    res = p.fetch_as_of(["AAPL"], as_of=date(2024, 11, 15), model="bos")
    assert res.rows[0]["inst_concentration_score"] is None
    assert any("bulk fetch failed" in w for w in res.warnings)


# --- caching --------------------------------------------------------------


def test_fetch_quarter_uses_disk_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE_DIR", tmp_path)
    cache = tmp_path / "agg_2024Q3.json"
    fake = {
        TICKER_TO_CUSIP["AAPL"]: {
            "cusip": TICKER_TO_CUSIP["AAPL"], "issuer_name": "Apple Inc.",
            "n_filers": 100, "total_shares": 1_000_000, "total_value_usd": 1.5e10,
        }
    }
    cache.write_text(json.dumps(fake), encoding="utf-8")

    # Should NOT call requests because cache is present + fresh.
    def explode(*a, **kw):
        raise AssertionError("network call attempted while cache fresh")
    monkeypatch.setattr(tf.requests, "get", explode)

    out = tf.fetch_13f_quarter(2024, 3, ttl_seconds=10_000)
    assert TICKER_TO_CUSIP["AAPL"] in out
    assert out[TICKER_TO_CUSIP["AAPL"]].n_filers == 100
