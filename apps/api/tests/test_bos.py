from trio_algorithms import BosWeights, score_bos


def _row(t, vol, ret, dvd, z, sent):
    return {
        "ticker": t,
        "vol_avg_3m": vol,
        "target_return": ret,
        "dvd_yld_ind": dvd,
        "altman_z": z,
        "analyst_sent": sent,
    }


def test_bos_strong_buy_scores_max():
    rows = [_row("STRONG", 1_000_000, 25, 7, 3.0, 4.5)]
    resp = score_bos(rows)
    assert resp.results[0].final_score == 3.0  # all factors at BUY=3 -> weighted total = 3
    assert all(f.band == "BUY" for f in resp.results[0].factors)


def test_bos_quartiles_assigned_with_universe_of_4():
    rows = [
        _row("BEST", 1_000_000, 25, 7, 3.0, 4.5),
        _row("OK_HIGH", 500_000, 20, 5, 2.5, 4.3),
        _row("OK_LOW", 350_000, 0, 4, 1.7, 3.5),
        _row("WORST", 100_000, -50, 1, 0.5, 1.0),
    ]
    resp = score_bos(rows)
    qs = {r.ticker: r.quartile for r in resp.results}
    assert qs["BEST"] == 1
    assert qs["WORST"] == 4


def test_bos_skips_quartiles_when_universe_too_small():
    rows = [_row("ONE", 500_000, 10, 5, 2.5, 4.0)]
    resp = score_bos(rows)
    assert resp.results[0].quartile is None
    assert "quartiles not assigned" in " ".join(resp.warnings).lower()


def test_bos_handles_missing_fields():
    rows = [
        {"ticker": "BAD", "vol_avg_3m": "#N/A Field Not Applicable"},
        {"ticker": "OK", "vol_avg_3m": 500_000, "target_return": 20,
         "dvd_yld_ind": 5, "altman_z": 2.5, "analyst_sent": 4.3},
    ]
    resp = score_bos(rows)
    bad = next(r for r in resp.results if r.ticker == "BAD")
    assert bad.final_score is None
    assert any("missing" in f.flags for f in bad.factors)


def test_bos_strips_percent_and_comma_from_strings():
    rows = [{
        "ticker": "STR",
        "vol_avg_3m": "1,200,000",
        "target_return": "20%",
        "dvd_yld_ind": "7.0",
        "altman_z": "2.8",
        "analyst_sent": "4.4",
    }]
    resp = score_bos(rows)
    # All five factors land in BUY (sub_score=3), weighted total = 3.0.
    assert resp.results[0].final_score == 3.0


def test_bos_custom_weights_change_ranking():
    """Tilt the engine toward dividend yield and the high-yield row should win."""
    rows = [
        # Z-hero: huge Altman-Z, weak yield
        _row("Z_HERO", 600_000, 18, 1.0, 5.0, 4.3),
        # YIELDER: massive yield, weak Z (clearly SELL band, <1.5)
        _row("YIELDER", 600_000, 18, 9.0, 1.4, 4.3),
    ]
    canonical = score_bos(rows)
    # Under canonical weights (Altman-Z 0.30 vs dividend 0.20), Z_HERO scores higher.
    canon_top = max(canonical.results, key=lambda r: r.final_score or -999)
    assert canon_top.ticker == "Z_HERO"

    yield_first = score_bos(
        rows,
        weights=BosWeights(
            f1_volume=0.05, f2_target=0.05, f3_dvd_yld=0.70,
            f4_altman_z=0.10, f5_analyst_sent=0.10,
        ),
    )
    # Tilting toward dividend yield flips the winner.
    yield_top = max(yield_first.results, key=lambda r: r.final_score or -999)
    assert yield_top.ticker == "YIELDER"
    assert any("overridden" in w.lower() for w in yield_first.warnings)


def test_bos_zero_total_weights_falls_back_to_canonical():
    rows = [_row("X", 600_000, 18, 6.5, 2.5, 4.3)]
    zero = BosWeights(f1_volume=0, f2_target=0, f3_dvd_yld=0, f4_altman_z=0, f5_analyst_sent=0)
    resp = score_bos(rows, weights=zero)
    # normalised() returns canonical defaults when sum is zero, so score is finite.
    assert resp.results[0].final_score is not None


def test_bos_custom_weights_normalised_sums_to_one():
    w = BosWeights(f1_volume=2, f2_target=2, f3_dvd_yld=2, f4_altman_z=2, f5_analyst_sent=2)
    n = w.normalised()
    total = n.f1_volume + n.f2_target + n.f3_dvd_yld + n.f4_altman_z + n.f5_analyst_sent
    assert abs(total - 1.0) < 1e-9

