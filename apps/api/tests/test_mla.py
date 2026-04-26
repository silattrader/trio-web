"""MLA v0 tests — training is fast (<2s on synthetic data) so we can train fresh."""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.main import app
from trio_algorithms import (
    MlaScorer,
    PromotionDecision,
    evaluate_promotion,
    score_bos,
    score_mla_v0,
)
from trio_algorithms.mla.train import build_dataset, train

client = TestClient(app)


def _row(t, vol, ret, dvd, z, sent):
    return {
        "ticker": t, "vol_avg_3m": vol, "target_return": ret,
        "dvd_yld_ind": dvd, "altman_z": z, "analyst_sent": sent,
    }


def test_build_dataset_is_deterministic_with_seed():
    X1, y1, _ = build_dataset(100, seed=42)
    X2, y2, _ = build_dataset(100, seed=42)
    assert (X1 == X2).all() and (y1 == y2).all()


def test_train_returns_a_fit_scorer():
    scorer = train(n_samples=500, seed=7)
    assert scorer.model is not None
    # r2 on training data should be reasonable for a smooth synthetic target.
    assert scorer.meta.train_r2 > 0.5
    # Strong correlation with RBA but not perfect — alpha term diverges.
    assert 0.5 < scorer.meta.rba_corr < 0.999


def test_score_mla_returns_same_contract_as_bos():
    rows = [
        _row("A", 1_000_000, 18, 4.5, 2.5, 4.3),
        _row("B", 500_000, 5, 3.0, 1.6, 3.4),
        _row("C", 300_000, -8, 0.5, 0.9, 2.5),
        _row("D", 800_000, 22, 6.0, 3.2, 4.5),
    ]
    bos = score_bos(rows)
    mla = score_mla_v0(rows)
    # Same number of results.
    assert len(mla.results) == len(bos.results)
    # Same contract: each result has the required fields.
    for r in mla.results:
        assert r.ticker
        assert r.recommendation is not None
        assert len(r.factors) == 5
    assert mla.model_version == "mla-v0.1.0"


def test_mla_handles_missing_factor_gracefully():
    rows = [
        _row("OK", 800_000, 18, 4.5, 2.5, 4.3),
        {"ticker": "BAD"},  # everything missing
    ]
    resp = score_mla_v0(rows)
    bad = next(r for r in resp.results if r.ticker == "BAD")
    assert bad.final_score is None


def test_score_endpoint_accepts_mla_v0():
    rows = [
        _row("A", 1_000_000, 18, 4.5, 2.5, 4.3),
        _row("B", 500_000, 5, 3.0, 1.6, 3.4),
        _row("C", 300_000, -8, 0.5, 0.9, 2.5),
        _row("D", 800_000, 22, 6.0, 3.2, 4.5),
    ]
    body = client.post(
        "/score?model=mla_v0",
        json={"universe": "TEST", "rows": rows},
    ).json()
    assert body["model_version"] == "mla-v0.1.0"
    assert len(body["results"]) == 4


# ----------------------------- promotion gate ----------------------------


@dataclass
class _FakeMetrics:
    cagr: float
    sharpe: float


def test_promotion_passes_when_mla_dominates():
    mla = _FakeMetrics(cagr=0.15, sharpe=1.4)
    rba = _FakeMetrics(cagr=0.10, sharpe=1.0)
    decision = evaluate_promotion(mla, rba)
    assert isinstance(decision, PromotionDecision)
    assert decision.promote is True
    assert decision.cagr_lift == pytest.approx(0.05)
    assert any("PROMOTE" in r for r in decision.reasons)


def test_promotion_blocks_when_cagr_drops():
    mla = _FakeMetrics(cagr=0.08, sharpe=1.5)
    rba = _FakeMetrics(cagr=0.10, sharpe=1.0)
    decision = evaluate_promotion(mla, rba)
    assert decision.promote is False
    assert any("BLOCK" in r for r in decision.reasons)


def test_promotion_blocks_when_sharpe_collapses():
    mla = _FakeMetrics(cagr=0.10, sharpe=0.5)
    rba = _FakeMetrics(cagr=0.10, sharpe=1.0)
    decision = evaluate_promotion(mla, rba)
    # CAGR tied (lift=0 ≥ 0) but Sharpe drop -0.5 < threshold -0.1.
    assert decision.promote is False


def test_save_load_roundtrip(tmp_path):
    scorer = train(n_samples=200, seed=1)
    artifact = tmp_path / "mla.joblib"
    scorer.save(artifact)
    loaded = MlaScorer.load(artifact)
    rows = [_row("X", 800_000, 18, 4.5, 2.5, 4.3)]
    assert loaded.score_row(rows[0]) == pytest.approx(scorer.score_row(rows[0]))
