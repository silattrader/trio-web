"""BOS-Flow 7-factor engine tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from trio_algorithms import BosFlowWeights, score_bos_flow

client = TestClient(app)


def _row(t, **kw):
    base = {
        "ticker": t,
        "vol_avg_3m": 800_000,
        "target_return": 18,
        "dvd_yld_ind": 5.0,
        "altman_z": 2.5,
        "analyst_sent": 4.3,
        "insider_flow": 3.0,    # neutral
        "retail_flow": 3.0,     # neutral
    }
    base.update(kw)
    return base


# ---- core scoring --------------------------------------------------------


def test_bos_flow_strong_buy_scores_max():
    """All 7 factors at BUY → final_score = 3.0 (BOS sub_score scale)."""
    rows = [_row(
        "STRONG", vol_avg_3m=1_000_000, target_return=25, dvd_yld_ind=7,
        altman_z=3.0, analyst_sent=4.5, insider_flow=5.0, retail_flow=5.0,
    )]
    resp = score_bos_flow(rows)
    assert resp.results[0].final_score == pytest.approx(3.0)
    assert resp.model_version == "rba-bos-flow-1.0.0"
    # All 7 factor breakdowns present.
    assert len(resp.results[0].factors) == 7


def test_bos_flow_strong_sell():
    """All factors weak → final_score near 1.0 (SELL band)."""
    rows = [_row(
        "WEAK", vol_avg_3m=100_000, target_return=-30, dvd_yld_ind=0,
        altman_z=0.5, analyst_sent=2.0, insider_flow=1.0, retail_flow=1.0,
    )]
    resp = score_bos_flow(rows)
    assert resp.results[0].final_score == pytest.approx(1.0, abs=0.05)


def test_bos_flow_quartiles_assigned():
    rows = [
        _row("BEST", vol_avg_3m=1_000_000, target_return=25, dvd_yld_ind=7,
             altman_z=3.0, analyst_sent=4.5, insider_flow=5.0, retail_flow=5.0),
        _row("OK_HIGH", insider_flow=4.0, retail_flow=3.0),
        _row("OK_LOW", target_return=0, dvd_yld_ind=4, insider_flow=2.0),
        _row("WORST", vol_avg_3m=100_000, target_return=-50, dvd_yld_ind=0,
             altman_z=0.5, analyst_sent=1.5, insider_flow=1.0, retail_flow=1.0),
    ]
    resp = score_bos_flow(rows)
    qs = {r.ticker: r.quartile for r in resp.results}
    assert qs["BEST"] == 1
    assert qs["WORST"] == 4


def test_bos_flow_handles_missing_flow_factors():
    """When upstream provider didn't supply insider/retail flow, treat as missing."""
    rows = [_row("MIX", insider_flow=None, retail_flow=None)]
    resp = score_bos_flow(rows)
    factors = {f.id: f for f in resp.results[0].factors}
    assert factors["F6"].raw is None and "missing" in factors["F6"].flags
    assert factors["F7"].raw is None and "missing" in factors["F7"].flags
    # Score still computed off the 5 BOS factors that are present.
    assert resp.results[0].final_score is not None


def test_bos_flow_band_mapping_for_prescored():
    """Prescored 1-5 maps to BUY/NEUTRAL/SELL bands sensibly."""
    rows = [
        _row("HOT_RETAIL", retail_flow=1.0),  # extreme attention spike
        _row("COLD_RETAIL", retail_flow=5.0),  # dormant
        _row("MID_RETAIL", retail_flow=3.0),
    ]
    resp = score_bos_flow(rows)
    bands = {
        r.ticker: next(f for f in r.factors if f.id == "F7").band
        for r in resp.results
    }
    assert bands["HOT_RETAIL"] == "SELL"
    assert bands["COLD_RETAIL"] == "BUY"
    assert bands["MID_RETAIL"] == "NEUTRAL"


# ---- weight overrides ----------------------------------------------------


def test_bos_flow_custom_weights_change_ranking():
    """Tilt heavily toward insider_flow → the insider-bullish row wins."""
    rows = [
        # Z-hero with weak insider activity
        _row("Z_HERO", altman_z=5.0, dvd_yld_ind=1.0, insider_flow=2.0),
        # Modest fundamentals but insiders piling in
        _row("INSIDER_DARLING", altman_z=1.4, dvd_yld_ind=2.0,
             analyst_sent=3.5, insider_flow=5.0, retail_flow=3.0),
    ]
    canonical = score_bos_flow(rows)
    canon_top = max(canonical.results, key=lambda r: r.final_score or -999)
    # Default weights favour fundamentals; Z_HERO usually wins.
    assert canon_top.ticker == "Z_HERO"

    insider_first = score_bos_flow(rows, weights=BosFlowWeights(
        f1_volume=0.05, f2_target=0.05, f3_dvd_yld=0.05,
        f4_altman_z=0.05, f5_analyst_sent=0.05,
        f6_insider_flow=0.70, f7_retail_flow=0.05,
    ))
    insider_top = max(insider_first.results, key=lambda r: r.final_score or -999)
    assert insider_top.ticker == "INSIDER_DARLING"
    assert any("overridden" in w.lower() for w in insider_first.warnings)


def test_bos_flow_zero_weights_falls_back_to_canonical():
    rows = [_row("X")]
    zero = BosFlowWeights(
        f1_volume=0, f2_target=0, f3_dvd_yld=0, f4_altman_z=0,
        f5_analyst_sent=0, f6_insider_flow=0, f7_retail_flow=0,
    )
    resp = score_bos_flow(rows, weights=zero)
    assert resp.results[0].final_score is not None


def test_bos_flow_weights_normalised_sums_to_one():
    w = BosFlowWeights(
        f1_volume=2, f2_target=2, f3_dvd_yld=2, f4_altman_z=2,
        f5_analyst_sent=2, f6_insider_flow=2, f7_retail_flow=2,
    )
    n = w.normalised()
    total = (n.f1_volume + n.f2_target + n.f3_dvd_yld + n.f4_altman_z
             + n.f5_analyst_sent + n.f6_insider_flow + n.f7_retail_flow)
    assert abs(total - 1.0) < 1e-9


# ---- API endpoint --------------------------------------------------------


def test_score_endpoint_accepts_bos_flow():
    rows = [
        _row("A", insider_flow=5.0, retail_flow=3.0),
        _row("B", target_return=5, insider_flow=3.0, retail_flow=2.0),
        _row("C", target_return=-8, dvd_yld_ind=0.5, altman_z=0.9,
             insider_flow=1.0, retail_flow=1.0),
        _row("D", target_return=22, dvd_yld_ind=6.0, altman_z=3.2,
             insider_flow=4.0, retail_flow=3.0),
    ]
    body = client.post(
        "/score?model=bos_flow",
        json={"universe": "TEST", "rows": rows},
    ).json()
    assert body["model_version"] == "rba-bos-flow-1.0.0"
    assert len(body["results"]) == 4
    # Each result has 7 factor breakdowns.
    assert all(len(r["factors"]) == 7 for r in body["results"])


def test_score_endpoint_accepts_bos_flow_weights():
    rows = [_row("A"), _row("B"), _row("C"), _row("D")]
    body = client.post(
        "/score?model=bos_flow",
        json={
            "universe": "TEST",
            "rows": rows,
            "bos_flow_weights": {
                "f1_volume": 0.05, "f2_target": 0.05, "f3_dvd_yld": 0.05,
                "f4_altman_z": 0.05, "f5_analyst_sent": 0.05,
                "f6_insider_flow": 0.40, "f7_retail_flow": 0.35,
            },
        },
    ).json()
    assert body["model_version"] == "rba-bos-flow-1.0.0"
    assert any("overridden" in w.lower() for w in body["warnings"])


def test_models_endpoint_lists_bos_flow():
    data = client.get("/models").json()
    rba_ids = [m["id"] for m in data["rba"]]
    assert "bos_flow" in rba_ids
