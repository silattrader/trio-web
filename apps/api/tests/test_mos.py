from trio_algorithms import score_mos


def _bs(ticker, *, cash=100, ar=50, inv=50, oca=20, ap=30, osl=20, stb=20, ncl=50,
        shares=100, px=10.0, tgt=12.0):
    return {
        "ticker": ticker,
        "cash_near_cash": cash,
        "accounts_receivable": ar,
        "inventories": inv,
        "other_current_assets": oca,
        "accounts_payable": ap,
        "other_st_liab": osl,
        "st_borrow": stb,
        "non_current_liab": ncl,
        "shares_out": shares,
        "px_last": px,
        "best_target_price": tgt,
    }


def test_mos_magic_no_lower_is_better():
    cheap = _bs("CHEAP", cash=500, px=5.0, tgt=10.0)        # high upside, lower premium
    expensive = _bs("EXP", cash=100, px=20.0, tgt=21.0)     # low upside, high premium
    resp = score_mos([cheap, expensive, _bs("A"), _bs("B")])
    cheap_r = next(r for r in resp.results if r.ticker == "CHEAP")
    exp_r = next(r for r in resp.results if r.ticker == "EXP")
    assert cheap_r.final_score < exp_r.final_score
    assert cheap_r.quartile <= exp_r.quartile  # cheap should rank better (lower q number)


def test_mos_excludes_no_upside_rows():
    no_upside = _bs("NOUP", px=15.0, tgt=10.0)  # target below price
    resp = score_mos([no_upside, _bs("A"), _bs("B"), _bs("C")])
    nu = next(r for r in resp.results if r.ticker == "NOUP")
    assert nu.quartile is None
    assert "no_upside" in nu.flags
