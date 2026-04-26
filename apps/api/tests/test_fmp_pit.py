"""FmpPitProvider + MergedPitProvider tests — fully mocked HTTP, no network."""
from __future__ import annotations

from datetime import date

import pytest

from trio_data_providers import (
    FmpPitProvider,
    MergedPitProvider,
    _fmp_client as fc,
)
from trio_data_providers.fmp_pit import (
    GRADE_TO_SCORE,
    _consensus_rating,
    _consensus_target,
    _normalise_grade,
    _parse_iso_date,
)


# ---- low-level helpers ---------------------------------------------------


def test_grade_to_score_covers_common_terms():
    assert GRADE_TO_SCORE["buy"] == 4.5
    assert GRADE_TO_SCORE["hold"] == 3.0
    assert GRADE_TO_SCORE["sell"] == 1.5
    assert GRADE_TO_SCORE["strong buy"] > GRADE_TO_SCORE["buy"]
    assert GRADE_TO_SCORE["strong sell"] < GRADE_TO_SCORE["sell"]


def test_normalise_grade_is_case_insensitive():
    assert _normalise_grade("BUY") == 4.5
    assert _normalise_grade("  Hold  ") == 3.0
    assert _normalise_grade("Underweight") == 2.0
    assert _normalise_grade("hyperbuy") is None  # unknown → None


def test_parse_iso_date_handles_datetime_strings():
    assert _parse_iso_date("2024-03-15") == date(2024, 3, 15)
    assert _parse_iso_date("2024-03-15T09:00:00.000Z") == date(2024, 3, 15)
    assert _parse_iso_date(None) is None
    assert _parse_iso_date("garbage") is None


def test_consensus_target_filters_to_window_and_excludes_future():
    as_of = date(2023, 6, 1)
    records = [
        {"publishedDate": "2023-04-15", "priceTarget": 200.0},  # in window
        {"publishedDate": "2023-05-20", "priceTarget": 220.0},  # in window
        {"publishedDate": "2022-01-01", "priceTarget": 150.0},  # too old
        {"publishedDate": "2023-07-01", "priceTarget": 999.0},  # FUTURE — must drop
    ]
    mean, n = _consensus_target(records, as_of=as_of, window_days=90)
    assert n == 2 and mean == pytest.approx(210.0)


def test_consensus_rating_aggregates_scores():
    as_of = date(2023, 6, 1)
    records = [
        {"publishedDate": "2023-05-01", "newGrade": "Buy"},      # 4.5
        {"publishedDate": "2023-05-15", "newGrade": "Hold"},     # 3.0
        {"publishedDate": "2023-05-25", "newGrade": "Outperform"},  # 4.5
        {"publishedDate": "2023-05-28", "newGrade": "WeirdGrade"},  # unmapped
    ]
    mean, n, unmapped = _consensus_rating(records, as_of=as_of, window_days=90)
    assert n == 3
    assert mean == pytest.approx((4.5 + 3.0 + 4.5) / 3)
    assert "WeirdGrade" in unmapped


# ---- provider integration with patched HTTP ------------------------------


@pytest.fixture
def patched_fmp(monkeypatch, tmp_path):
    """Replace network with deterministic in-memory fixtures."""
    monkeypatch.setattr(fc, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("TRIO_FMP_KEY", "test-key-not-real")

    targets_db = {
        "AAPL": [
            {"publishedDate": "2023-04-10", "priceTarget": 180.0},
            {"publishedDate": "2023-05-15", "priceTarget": 200.0},
            {"publishedDate": "2023-05-25", "priceTarget": 210.0},
            {"publishedDate": "2023-07-01", "priceTarget": 999.0},  # future
        ],
        "MSFT": [],  # no targets
    }
    ratings_db = {
        "AAPL": [
            {"publishedDate": "2023-05-10", "newGrade": "Buy"},
            {"publishedDate": "2023-05-20", "newGrade": "Outperform"},
            {"publishedDate": "2023-05-25", "newGrade": "Hold"},
        ],
        "MSFT": [
            {"publishedDate": "2023-05-15", "newGrade": "Sell"},
        ],
    }

    def _fake_targets(ticker, *, ttl_seconds=fc.DEFAULT_TTL_SECONDS):
        return list(targets_db.get(ticker.upper(), []))

    def _fake_ratings(ticker, *, ttl_seconds=fc.DEFAULT_TTL_SECONDS):
        return list(ratings_db.get(ticker.upper(), []))

    monkeypatch.setattr(fc, "fetch_price_targets", _fake_targets)
    monkeypatch.setattr(fc, "fetch_upgrades_downgrades", _fake_ratings)
    return {"targets": targets_db, "ratings": ratings_db}


def test_fmp_pit_fills_target_return_and_analyst_sent(patched_fmp):
    p = FmpPitProvider()
    prices = {
        "AAPL": {date(2023, 5, 30): 175.0},
        "MSFT": {date(2023, 5, 30): 320.0},
    }
    res = p.fetch_as_of(
        ["AAPL", "MSFT"], as_of=date(2023, 6, 1), model="bos", prices=prices,
    )
    aapl = next(r for r in res.rows if r["ticker"] == "AAPL")
    msft = next(r for r in res.rows if r["ticker"] == "MSFT")

    # 3 targets in window with mean (180+200+210)/3 = 196.67; price 175.
    # target_return = (196.67 − 175) / 175 = ~12.38%
    assert aapl["target_return"] == pytest.approx((196.6667 - 175) / 175 * 100, abs=0.05)
    # 3 ratings in window: Buy(4.5) + Outperform(4.5) + Hold(3.0) → mean 4.0
    assert aapl["analyst_sent"] == pytest.approx(4.0, abs=0.001)
    # MSFT: no targets → target_return None.
    assert msft["target_return"] is None
    # MSFT: one Sell rating → analyst_sent 1.5
    assert msft["analyst_sent"] == 1.5


def test_fmp_pit_target_requires_price(patched_fmp):
    p = FmpPitProvider()
    res = p.fetch_as_of(["AAPL"], as_of=date(2023, 6, 1), model="bos")
    # No prices supplied → target_return must be None.
    assert res.rows[0]["target_return"] is None
    # analyst_sent still works without prices.
    assert res.rows[0]["analyst_sent"] is not None
    assert any("prices= not supplied" in w for w in res.warnings)


def test_fmp_pit_window_excludes_old_data(patched_fmp):
    """As-of in 2024 — all fixture targets/ratings are stale (>90d)."""
    p = FmpPitProvider()
    res = p.fetch_as_of(
        ["AAPL"], as_of=date(2024, 6, 1), model="bos",
        prices={"AAPL": {date(2024, 5, 30): 200.0}},
    )
    assert res.rows[0]["target_return"] is None
    assert res.rows[0]["analyst_sent"] is None


# ---- merged provider -----------------------------------------------------


class _StubProvider:
    """Minimal stub for testing merge logic without HTTP."""
    name = "stub"
    label = "stub"

    def __init__(self, name: str, rows: list[dict]) -> None:
        self.name = name
        self._rows = rows

    def fetch_as_of(self, tickers, *, as_of, model, prices=None, volumes=None):
        from trio_data_providers.pit import PitResult
        return PitResult(
            rows=[dict(r) for r in self._rows],
            as_of=as_of, provider=self.name, warnings=[f"{self.name} ran"],
        )


def test_merged_pit_combines_factors():
    edgar_like = _StubProvider("edgar", [
        {"ticker": "AAPL", "altman_z": 2.5, "dvd_yld_ind": 0.5,
         "vol_avg_3m": 5e7, "target_return": None, "analyst_sent": None},
    ])
    fmp_like = _StubProvider("fmp", [
        {"ticker": "AAPL", "altman_z": None, "dvd_yld_ind": None,
         "vol_avg_3m": None, "target_return": 12.4, "analyst_sent": 4.0},
    ])
    merged = MergedPitProvider([edgar_like, fmp_like])
    res = merged.fetch_as_of(["AAPL"], as_of=date(2023, 6, 1), model="bos")
    row = res.rows[0]
    # All 5 factors filled.
    assert row["altman_z"] == 2.5
    assert row["dvd_yld_ind"] == 0.5
    assert row["vol_avg_3m"] == 5e7
    assert row["target_return"] == 12.4
    assert row["analyst_sent"] == 4.0
    assert any("factor coverage" in w for w in res.warnings)
    # Underlying provider warnings prefixed with name.
    assert any("[edgar]" in w for w in res.warnings)
    assert any("[fmp]" in w for w in res.warnings)


def test_merged_first_provider_wins_when_both_have_value():
    a = _StubProvider("a", [{"ticker": "AAPL", "altman_z": 2.0}])
    b = _StubProvider("b", [{"ticker": "AAPL", "altman_z": 9.9}])
    merged = MergedPitProvider([a, b])
    res = merged.fetch_as_of(["AAPL"], as_of=date(2023, 6, 1), model="bos")
    # Last-non-None-wins logic preserves a's value since it isn't None.
    assert res.rows[0]["altman_z"] == 2.0
