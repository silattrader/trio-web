"""InsiderFlowPitProvider + Form 4 client tests — fully mocked HTTP."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from trio_data_providers import InsiderFlowPitProvider
from trio_data_providers import _edgar_client as ec
from trio_data_providers import _edgar_form4 as f4
from trio_data_providers.insider_pit import score_from_normalised_flow


def _form4_xml(transactions: list[tuple], *, is_director: bool = True) -> str:
    """Build a minimal Form 4 XML fixture.

    transactions = [(tx_date_iso, shares, price, ad_code, tx_code), ...]
    ad_code: 'A' (acquired) or 'D' (disposed).
    tx_code: 'P' (open-market buy), 'S' (open-market sell), 'M' (option exercise), etc.
    Tuples of length 4 default tx_code based on ad_code: 'A'->'P', 'D'->'S'.
    """
    def expand(t):
        if len(t) == 5:
            return t
        d, s, p, ad = t
        return d, s, p, ad, "P" if ad == "A" else "S"

    items = "".join(
        f"""<nonDerivativeTransaction>
            <transactionDate><value>{d}</value></transactionDate>
            <transactionCoding>
                <transactionCode>{tc}</transactionCode>
            </transactionCoding>
            <transactionAmounts>
                <transactionShares><value>{s}</value></transactionShares>
                <transactionPricePerShare><value>{p}</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
        </nonDerivativeTransaction>"""
        for d, s, p, ad, tc in (expand(t) for t in transactions)
    )
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerRelationship>
      <isDirector>{1 if is_director else 0}</isDirector>
      <isOfficer>0</isOfficer>
      <officerTitle>Director</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    {items}
  </nonDerivativeTable>
</ownershipDocument>"""


# ---- score_from_normalised_flow ------------------------------------------


def test_score_thresholds():
    assert score_from_normalised_flow(0.10) == 5.0      # heavy buying
    assert score_from_normalised_flow(0.01) == 4.0      # mild buying
    assert score_from_normalised_flow(0.0) == 3.0       # neutral
    assert score_from_normalised_flow(-0.01) == 2.0     # mild selling
    assert score_from_normalised_flow(-0.10) == 1.0     # heavy selling


def test_score_boundaries():
    # On-the-edge values land in the higher band per the >= comparisons.
    assert score_from_normalised_flow(0.025) == 5.0
    assert score_from_normalised_flow(0.005) == 4.0
    assert score_from_normalised_flow(-0.005) == 3.0
    assert score_from_normalised_flow(-0.025) == 2.0


# ---- parse_form4 ---------------------------------------------------------


def test_parse_form4_picks_up_buys_and_sells():
    xml = _form4_xml([
        ("2023-05-10", 1000, 150.0, "A"),
        ("2023-05-15", 500, 155.0, "D"),
    ])
    txs = f4.parse_form4(xml, accession="ACC", filed=date(2023, 5, 16))
    assert len(txs) == 2
    buys = [t for t in txs if t.acquired]
    sells = [t for t in txs if not t.acquired]
    assert len(buys) == 1 and len(sells) == 1
    assert buys[0].shares == 1000 and buys[0].price == 150.0
    # Signed value: buy adds, sell subtracts
    assert buys[0].signed_value_usd == 150_000
    assert sells[0].signed_value_usd == -77_500


def test_parse_form4_handles_empty_table():
    assert f4.parse_form4("<?xml version='1.0'?><ownershipDocument/>") == []


def test_parse_form4_skips_zero_share_rows():
    xml = _form4_xml([("2023-05-10", 0, 100.0, "A")])
    assert f4.parse_form4(xml) == []


def test_insider_flow_filters_to_discretionary_codes(monkeypatch):
    """RSU vests (M), gifts (G), tax-withholding (F), and grants (A) should
    be excluded — only open-market P/S transactions count toward the flow score."""
    monkeypatch.setattr(ec, "fetch_ticker_map", lambda **kw: {"ACME": "0001234567"})

    # Mix of codes: only the P should count.
    xml = _form4_xml([
        ("2023-05-10", 1000, 150.0, "A", "P"),  # open-market buy — counts
        ("2023-05-12", 5000, 0.0,   "A", "M"),  # RSU vest — drop
        ("2023-05-14", 200,  150.0, "D", "F"),  # tax withholding — drop
        ("2023-05-16", 100,  150.0, "D", "G"),  # gift — drop
        ("2023-05-18", 800,  155.0, "A", "A"),  # grant — drop
    ])
    monkeypatch.setattr(f4, "fetch_recent_form4_index", lambda cik, **kw: [{
        "accessionNumber": "0001-23-100", "filingDate": "2023-05-20",
        "primaryDocument": "wf.xml", "reportDate": "2023-05-18",
    }])
    monkeypatch.setattr(f4, "fetch_form4_filing", lambda *a, **kw: xml)

    p = InsiderFlowPitProvider(lookback_days=90)
    res = p.fetch_as_of(
        ["ACME"], as_of=date(2023, 6, 1), model="bos",
        prices={"ACME": {date(2023, 5, 1): 150.0}},
        volumes={"ACME": {date(2023, 5, 1): 1_000.0}},
    )
    row = res.rows[0]
    assert row["_insider_n_transactions"] == 1  # only the P=open-market buy
    assert row["_insider_n_buys"] == 1
    assert row["_insider_net_usd"] == 150_000  # 1000 × 150


# ---- end-to-end provider with patched HTTP ------------------------------


@pytest.fixture
def patched_form4(monkeypatch, tmp_path):
    """Stub out EDGAR ticker map + Form 4 fetch."""
    # Reuse EdgarPitProvider's CIK mapping by patching the underlying lookup.
    monkeypatch.setattr(ec, "fetch_ticker_map", lambda **kw: {"ACME": "0001234567"})

    # 3 filings: 2 buys, 1 sell, and 1 too-old to count.
    filings = [
        {
            "accessionNumber": "0001-23-001",
            "filingDate": "2023-05-12",
            "primaryDocument": "wf1.xml",
            "reportDate": "2023-05-10",
        },
        {
            "accessionNumber": "0001-23-002",
            "filingDate": "2023-05-25",
            "primaryDocument": "wf2.xml",
            "reportDate": "2023-05-22",
        },
        {
            "accessionNumber": "0001-23-003",
            "filingDate": "2023-04-20",
            "primaryDocument": "wf3.xml",
            "reportDate": "2023-04-18",
        },
        {
            "accessionNumber": "0001-22-099",
            "filingDate": "2022-12-01",  # outside 90d window from as_of=2023-06-01
            "primaryDocument": "old.xml",
            "reportDate": "2022-11-30",
        },
    ]
    xml_by_doc = {
        "wf1.xml": _form4_xml([("2023-05-10", 5000, 100.0, "A")]),       # +500k
        "wf2.xml": _form4_xml([("2023-05-22", 1000, 105.0, "D")]),       # -105k
        "wf3.xml": _form4_xml([("2023-04-18", 2000, 95.0, "A")]),         # +190k
        "old.xml": _form4_xml([("2022-11-30", 99999, 1.0, "D")]),        # ignored
    }

    def fake_index(cik, *, ttl_seconds=f4.DEFAULT_TTL_SECONDS):
        return list(filings)

    def fake_filing(cik, accession_no, primary_doc, *, ttl_seconds=f4.DEFAULT_TTL_SECONDS):
        return xml_by_doc[primary_doc]

    monkeypatch.setattr(f4, "fetch_recent_form4_index", fake_index)
    monkeypatch.setattr(f4, "fetch_form4_filing", fake_filing)
    return {"filings": filings, "xml": xml_by_doc}


def test_insider_flow_normalised_buy_signal(patched_form4):
    """Net buying of $585k vs $5k/day dvol → 117 days = saturated to 5.0."""
    p = InsiderFlowPitProvider(lookback_days=90)
    base = date(2023, 3, 1)
    prices = {"ACME": {base + timedelta(days=i): 100.0 for i in range(120)}}
    volumes = {"ACME": {base + timedelta(days=i): 50.0 for i in range(120)}}  # $5k/day dvol
    res = p.fetch_as_of(
        ["ACME"], as_of=date(2023, 6, 1), model="bos",
        prices=prices, volumes=volumes,
    )
    row = res.rows[0]
    # net_usd = 500_000 + 190_000 - 105_000 = 585_000; dvol = 5_000; ratio 117 → score 5
    assert row["_insider_n_transactions"] == 3  # the 4th was outside the window
    assert row["_insider_net_usd"] == 585_000
    assert row["insider_flow"] == 5.0
    assert row["_insider_score_kind"] == "normalised"


def test_insider_flow_neutral_when_no_filings(patched_form4, monkeypatch):
    monkeypatch.setattr(f4, "fetch_recent_form4_index", lambda cik, **kw: [])
    p = InsiderFlowPitProvider(lookback_days=90)
    res = p.fetch_as_of(
        ["ACME"], as_of=date(2023, 6, 1), model="bos",
        prices={"ACME": {date(2023, 5, 1): 100.0}},
        volumes={"ACME": {date(2023, 5, 1): 1_000.0}},
    )
    row = res.rows[0]
    assert row["insider_flow"] == 3.0
    assert row["_insider_score_kind"] == "neutral_quiet"


def test_insider_flow_falls_back_to_sign_only_without_dvol(patched_form4):
    """No prices/volumes → can't normalise; falls back to sign-only scoring."""
    p = InsiderFlowPitProvider(lookback_days=90)
    res = p.fetch_as_of(["ACME"], as_of=date(2023, 6, 1), model="bos")
    row = res.rows[0]
    # net is positive → scores 4.0 (buy), not the saturated 5.0
    assert row["insider_flow"] == 4.0
    assert row["_insider_score_kind"] == "sign_only_fallback"
    assert any("sign-only" in w for w in res.warnings)


def test_insider_flow_excludes_filings_outside_lookback(patched_form4):
    """as_of in 2024 — all the May-2023 filings are now stale (>90d)."""
    p = InsiderFlowPitProvider(lookback_days=90)
    res = p.fetch_as_of(["ACME"], as_of=date(2024, 3, 1), model="bos",
                       prices={"ACME": {date(2024, 2, 1): 100.0}},
                       volumes={"ACME": {date(2024, 2, 1): 100.0}})
    # No filings in window → neutral_quiet path.
    assert res.rows[0]["_insider_score_kind"] == "neutral_quiet"


def test_insider_flow_unknown_ticker_no_cik(patched_form4):
    p = InsiderFlowPitProvider()
    res = p.fetch_as_of(["NOTREAL"], as_of=date(2023, 6, 1), model="bos")
    assert res.rows[0]["insider_flow"] is None
    assert any("no CIK match" in w for w in res.warnings)
