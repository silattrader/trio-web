"""Quality-Value (QV) 6-factor engine tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from trio_algorithms import QvWeights, score_qv

client = TestClient(app)


def _row(t, **kw):
    """Default to a 'good' company across all 6 QV factors. Override per test."""
    base = {
        "ticker": t,
        "roe": 18.0,                       # > 15 (BUY)
        "gross_profit_to_assets": 0.35,    # > 0.30 (BUY)
        "debt_to_equity": 0.4,             # < 0.5 (BUY — reversed)
        "earnings_yield": 10.0,            # > 8 (BUY)
        "book_to_market": 0.7,             # > 0.6 (BUY)
        "fcf_yield": 7.0,                  # > 6 (BUY)
    }
    base.update(kw)
    return base


# ---- core scoring ----------------------------------------------------------


def test_qv_strong_buy_scores_max():
    """All 6 factors at BUY → final_score = 3.0 (BOS sub-score scale)."""
    rows = [_row("STRONG")]
    resp = score_qv(rows)
    assert resp.results[0].final_score == pytest.approx(3.0)
    assert resp.model_version == "rba-qv-1.0.0"
    assert len(resp.results[0].factors) == 6


def test_qv_strong_sell_scores_min():
    """All 6 factors at SELL → final_score = 1.0."""
    rows = [_row(
        "WEAK",
        roe=2.0, gross_profit_to_assets=0.05, debt_to_equity=2.5,
        earnings_yield=0.5, book_to_market=0.1, fcf_yield=0.5,
    )]
    resp = score_qv(rows)
    assert resp.results[0].final_score == pytest.approx(1.0, abs=0.05)


def test_qv_debt_to_equity_is_reversed():
    """LOWER d/e is better — verify the reversed banding."""
    low_debt = score_qv([_row("LOW", debt_to_equity=0.3)])
    high_debt = score_qv([_row("HIGH", debt_to_equity=2.0)])
    f3_low = next(f for f in low_debt.results[0].factors if f.id == "F3")
    f3_high = next(f for f in high_debt.results[0].factors if f.id == "F3")
    assert f3_low.band == "BUY"
    assert f3_low.sub_score == 3.0
    assert f3_high.band == "SELL"
    assert f3_high.sub_score == 1.0


def test_qv_neutral_factors_score_2():
    """A row in the NEUTRAL band for every factor → final_score = 2.0."""
    rows = [_row(
        "MID",
        roe=10.0, gross_profit_to_assets=0.2, debt_to_equity=1.0,
        earnings_yield=5.0, book_to_market=0.4, fcf_yield=4.0,
    )]
    resp = score_qv(rows)
    assert resp.results[0].final_score == pytest.approx(2.0)
    for f in resp.results[0].factors:
        assert f.band == "NEUTRAL"


def test_qv_quartiles_ranked_by_score():
    rows = [
        _row("BEST", roe=25, gross_profit_to_assets=0.5, debt_to_equity=0.2,
             earnings_yield=15, book_to_market=1.0, fcf_yield=10),
        _row("OK_HIGH"),
        _row("OK_LOW", roe=10, gross_profit_to_assets=0.2, debt_to_equity=1.0,
             earnings_yield=5, book_to_market=0.4, fcf_yield=4),
        _row("WORST", roe=2, gross_profit_to_assets=0.05, debt_to_equity=2.5,
             earnings_yield=0.5, book_to_market=0.1, fcf_yield=0.5),
    ]
    resp = score_qv(rows)
    qs = {r.ticker: r.quartile for r in resp.results}
    assert qs["BEST"] == 1
    assert qs["WORST"] == 4


def test_qv_handles_missing_factors():
    """Missing factor → flagged, not zeroed; partial score still computed."""
    rows = [_row(
        "PARTIAL",
        roe=None, gross_profit_to_assets=None,    # 2 quality factors missing
    )]
    resp = score_qv(rows)
    factors = {f.id: f for f in resp.results[0].factors}
    assert "missing" in factors["F1"].flags
    assert "missing" in factors["F2"].flags
    assert factors["F1"].band == "N/A" and factors["F1"].sub_score == 0
    assert factors["F2"].band == "N/A" and factors["F2"].sub_score == 0
    # Final score still computed off the 4 present factors.
    assert resp.results[0].final_score is not None


def test_qv_completely_missing_row_returns_none():
    """Row with NO factor data → final_score=None, recommendation=UNRANKED."""
    rows = [{"ticker": "EMPTY"}]
    resp = score_qv(rows)
    assert resp.results[0].final_score is None
    assert resp.results[0].recommendation == "UNRANKED"


# ---- weight overrides -----------------------------------------------------


def test_qv_custom_weights_can_flip_ranking():
    """Verify that tilting weights toward value flips the ranking.

    Canonical weights give 50% quality / 50% value, so two rows that are
    quality-strong + value-weak vs quality-weak + value-strong tie exactly
    at 2.50 (intentional symmetry — neither bias is preferred by default).
    Override toward value → value-strong wins. Override toward quality →
    quality-strong wins. Both directions tested.
    """
    rows = [
        # Quality king: max quality, neutral value
        _row("QUALITY_KING",
             roe=25, gross_profit_to_assets=0.5, debt_to_equity=0.2,
             earnings_yield=4, book_to_market=0.3, fcf_yield=3),
        # Value bargain: neutral quality, max value
        _row("VALUE_BARGAIN",
             roe=8, gross_profit_to_assets=0.15, debt_to_equity=1.2,
             earnings_yield=15, book_to_market=1.2, fcf_yield=12),
    ]

    # Tilt heavily toward value → VALUE_BARGAIN wins
    value_first = score_qv(rows, weights=QvWeights(
        f1_roe=0.05, f2_gross_profit_to_assets=0.05, f3_debt_to_equity=0.05,
        f4_earnings_yield=0.50, f5_book_to_market=0.20, f6_fcf_yield=0.15,
    ))
    value_top = max(value_first.results, key=lambda r: r.final_score or -999)
    assert value_top.ticker == "VALUE_BARGAIN"
    assert any("overridden" in w.lower() for w in value_first.warnings)

    # Tilt heavily toward quality → QUALITY_KING wins
    quality_first = score_qv(rows, weights=QvWeights(
        f1_roe=0.30, f2_gross_profit_to_assets=0.40, f3_debt_to_equity=0.20,
        f4_earnings_yield=0.05, f5_book_to_market=0.03, f6_fcf_yield=0.02,
    ))
    quality_top = max(quality_first.results, key=lambda r: r.final_score or -999)
    assert quality_top.ticker == "QUALITY_KING"


def test_qv_zero_total_weights_falls_back_to_canonical():
    rows = [_row("X")]
    zero = QvWeights(
        f1_roe=0, f2_gross_profit_to_assets=0, f3_debt_to_equity=0,
        f4_earnings_yield=0, f5_book_to_market=0, f6_fcf_yield=0,
    )
    resp = score_qv(rows, weights=zero)
    assert resp.results[0].final_score is not None


def test_qv_weights_normalised_sums_to_one():
    w = QvWeights(
        f1_roe=2, f2_gross_profit_to_assets=2, f3_debt_to_equity=2,
        f4_earnings_yield=2, f5_book_to_market=2, f6_fcf_yield=2,
    )
    n = w.normalised()
    total = (n.f1_roe + n.f2_gross_profit_to_assets + n.f3_debt_to_equity
             + n.f4_earnings_yield + n.f5_book_to_market + n.f6_fcf_yield)
    assert abs(total - 1.0) < 1e-9


# ---- API endpoint ---------------------------------------------------------


def test_score_endpoint_accepts_qv():
    rows = [
        _row("A"),
        _row("B", roe=8, earnings_yield=4),
        _row("C", roe=12, earnings_yield=6, debt_to_equity=1.0),
        _row("D", roe=2, gross_profit_to_assets=0.05, debt_to_equity=2.5,
             earnings_yield=0.5, book_to_market=0.1, fcf_yield=0.5),
    ]
    body = client.post(
        "/score?model=qv",
        json={"universe": "TEST", "rows": rows},
    ).json()
    assert body["model_version"] == "rba-qv-1.0.0"
    assert len(body["results"]) == 4
    assert all(len(r["factors"]) == 6 for r in body["results"])


def test_score_endpoint_accepts_qv_weights_override():
    rows = [_row("A"), _row("B"), _row("C"), _row("D")]
    body = client.post(
        "/score?model=qv",
        json={
            "universe": "TEST",
            "rows": rows,
            "qv_weights": {
                "f1_roe": 0.05, "f2_gross_profit_to_assets": 0.05,
                "f3_debt_to_equity": 0.05, "f4_earnings_yield": 0.60,
                "f5_book_to_market": 0.15, "f6_fcf_yield": 0.10,
            },
        },
    ).json()
    assert any("overridden" in w.lower() for w in body["warnings"])


def test_models_endpoint_lists_qv():
    data = client.get("/models").json()
    rba_ids = [m["id"] for m in data["rba"]]
    assert "qv" in rba_ids
