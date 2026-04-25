from trio_algorithms import score_four_factor


def _row(t, **kw):
    base = {"ticker": t, "altman_z": 2.5, "dvd_yld_est": 4.0,
            "roe_3yr_avg": 15.0, "pe_ratio": 10.0, "pe_5yr_avg": 14.0}
    base.update(kw)
    return base


def test_legacy_excludes_f3_corrected_includes_it():
    rows = [_row(f"S{i}", roe_3yr_avg=20.0 + i) for i in range(8)]
    legacy = score_four_factor(rows, legacy=True)
    fixed = score_four_factor(rows, legacy=False)
    legacy_score = legacy.results[0].final_score or 0
    fixed_score = fixed.results[0].final_score or 0
    assert fixed_score >= legacy_score  # F3 contribution non-negative
    assert legacy.model_version.endswith("legacy-1.0.0")
    assert fixed.model_version == "rba-four-factor-1.0.0"


def test_universe_relative_dvd_yield():
    # Universe mean = 5; row 1 above mean -> BUY (1.0), row 2 below -> SELL (0.5)
    rows = [_row("HI", dvd_yld_est=8.0), _row("LO", dvd_yld_est=2.0),
            _row("A"), _row("B")]
    resp = score_four_factor(rows)
    hi = next(r for r in resp.results if r.ticker == "HI")
    lo = next(r for r in resp.results if r.ticker == "LO")
    f2_hi = next(f for f in hi.factors if f.id == "F2")
    f2_lo = next(f for f in lo.factors if f.id == "F2")
    assert f2_hi.sub_score == 1.0
    assert f2_lo.sub_score == 0.5
