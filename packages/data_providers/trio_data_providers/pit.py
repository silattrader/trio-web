"""Point-in-time (PIT) fundamental data — Path 3.

Plain `DataProvider` returns *today's* fundamentals. A PIT provider returns the
fundamentals a CRO would have seen on a given historical date — the right
input for an honest backtest.

Two implementations live here:

* ``MockPitProvider`` — deterministic synthetic time-series. Same ticker on the
  same date always returns the same numbers. Clearly labelled as synthetic via
  the ``synthetic_pit`` warning on every result. Useful to demo the
  architecture end-to-end without a paid feed.

* ``EdgarPitProvider`` — skeleton for a real SEC EDGAR Companyfacts adapter.
  Computes Altman-Z components and dividend-yield from XBRL filings, as-of a
  date. Requires User-Agent header per SEC rules. Marked as a follow-up; not
  wired in by default.

Either way, two BOS factors (analyst sentiment, target return) cannot be
recovered point-in-time from filings — they are forward-looking by nature.
PIT providers fall back to today's snapshot for those and emit a warning.
"""
from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class PitResult:
    rows: list[dict[str, Any]]
    as_of: date
    provider: str
    warnings: list[str] = field(default_factory=list)


class PitProvider(ABC):
    name: str
    label: str

    @abstractmethod
    def fetch_as_of(
        self, tickers: list[str], *, as_of: date, model: str
    ) -> PitResult:
        """Pull canonical-field rows for these tickers as-of `as_of`."""


# --------------------------------------------------------------------------
# MockPitProvider — synthetic but deterministic
# --------------------------------------------------------------------------


def _hash_to_unit(*parts: str) -> float:
    """Deterministic [0, 1) value from arbitrary string parts."""
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _seasonal(t: float, period: float = 365.25) -> float:
    """Smooth wave in [-1, 1]; gives time-varying drift to mock fundamentals."""
    return math.sin(2 * math.pi * t / period)


class MockPitProvider(PitProvider):
    """Deterministic synthetic PIT data.

    For ticker T on date D:
    - vol_avg_3m ~ U(200_000, 1_500_000) anchored on hash(T) ± seasonal drift
    - target_return ~ N(8, 12) shifted by year-progress
    - dvd_yld_ind ~ U(0, 8) anchored on hash(T)
    - altman_z ~ U(0.5, 4.0) anchored on hash(T) + slow drift
    - analyst_sent ~ U(2.0, 4.7) anchored on hash(T)

    Different tickers get different "personalities"; the same ticker drifts
    smoothly over time, so re-scoring at different dates produces stable but
    not identical rankings.
    """

    name = "mock_pit"
    label = "Mock point-in-time (synthetic, deterministic)"

    def fetch_as_of(
        self, tickers: list[str], *, as_of: date, model: str
    ) -> PitResult:
        rows: list[dict[str, Any]] = []
        # Anchor t-coordinate on epoch-day so "drift" is cross-call stable.
        t = (as_of - date(2000, 1, 1)).days
        for tk in tickers:
            base = _hash_to_unit(tk, "anchor")
            # Slow seasonal drift, ticker-specific phase.
            phase = _hash_to_unit(tk, "phase") * 365.25
            drift = _seasonal(t + phase, period=365.25 * 2)  # 2-year cycle

            vol = 200_000 + base * 1_300_000 + drift * 200_000
            tgt = 8 + (base - 0.5) * 24 + drift * 6  # ranges roughly [-15, 30]
            dvd = base * 8 + drift * 0.5
            altz = 0.5 + base * 3.5 + drift * 0.5
            sent = 2.0 + base * 2.7 + drift * 0.3

            rows.append({
                "ticker": tk,
                "name": tk,
                "vol_avg_3m": max(0.0, vol),
                "target_return": tgt,
                "dvd_yld_ind": max(0.0, dvd),
                "altman_z": max(0.1, altz),
                "analyst_sent": max(1.0, min(5.0, sent)),
            })
        return PitResult(
            rows=rows,
            as_of=as_of,
            provider=self.name,
            warnings=[
                f"synthetic_pit: MockPitProvider produced as-of {as_of.isoformat()} "
                "data — deterministic but not real. Demo only; replace with EDGAR/Sharadar "
                "for publishable numbers."
            ],
        )


# --------------------------------------------------------------------------
# EdgarPitProvider — skeleton for real point-in-time XBRL data
# --------------------------------------------------------------------------


class EdgarPitProvider(PitProvider):
    """SEC EDGAR Companyfacts adapter — point-in-time fundamentals from XBRL.

    For each (ticker, as_of) we look up the CIK and pull the full Companyfacts
    blob, then for each Altman-Z component we pick the most recent reported
    value whose ``filed <= as_of`` — that's the no-lookahead invariant.

    Computes Altman Z' (private-firm variant) so we don't need a market-cap
    component the API can't supply directly:

        Z' = 0.717·WC/TA + 0.847·RE/TA + 3.107·EBIT/TA
           + 0.420·BookValue/Liab + 0.998·Sales/TA

    Trailing-12-month ``CommonStockDividendsPerShareDeclared`` divided by
    ``BookValuePerShare`` (or fallback to ``StockholdersEquity / SharesOutstanding``)
    gives an as-of dividend yield proxy.

    Three BOS factors are NOT recoverable point-in-time from filings:
    ``vol_avg_3m`` (price data, not financials), ``target_return`` (forward-
    looking analyst), ``analyst_sent`` (forward-looking analyst). We surface
    them as None and flag ``pit_unavailable`` per row — the BOS engine
    handles missing factors as NEUTRAL contributions.

    Networking + caching live in ``_edgar_client.py``. Set ``TRIO_SEC_UA``
    env to your contact email per SEC rules.
    """

    name = "edgar_pit"
    label = "SEC EDGAR Companyfacts (point-in-time)"

    # XBRL tags we consult. Tuples = (namespace, tag, unit, annual_only).
    # Multiple tags per concept handle issuer-specific reporting differences.
    _TAGS_TOTAL_ASSETS = [("us-gaap", "Assets", "USD", True)]
    _TAGS_LIABILITIES = [("us-gaap", "Liabilities", "USD", True)]
    _TAGS_CURRENT_ASSETS = [("us-gaap", "AssetsCurrent", "USD", True)]
    _TAGS_CURRENT_LIAB = [("us-gaap", "LiabilitiesCurrent", "USD", True)]
    _TAGS_RETAINED = [
        ("us-gaap", "RetainedEarningsAccumulatedDeficit", "USD", True),
    ]
    _TAGS_EBIT = [
        ("us-gaap", "OperatingIncomeLoss", "USD", True),
        ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "USD", True),
    ]
    _TAGS_REVENUE = [
        ("us-gaap", "Revenues", "USD", True),
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD", True),
        ("us-gaap", "SalesRevenueNet", "USD", True),
    ]
    _TAGS_EQUITY = [
        ("us-gaap", "StockholdersEquity", "USD", True),
        ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "USD", True),
    ]
    _TAGS_SHARES_OUT = [
        ("dei", "EntityCommonStockSharesOutstanding", "shares", False),
    ]
    _TAGS_DIVIDENDS_PS = [
        ("us-gaap", "CommonStockDividendsPerShareDeclared", "USD/shares", False),
    ]

    def __init__(self, *, ttl_seconds: int = 24 * 3600) -> None:
        self._ttl = ttl_seconds
        self._ticker_map: dict[str, str] | None = None

    def _ensure_map(self) -> dict[str, str]:
        from . import _edgar_client as ec
        if self._ticker_map is None:
            self._ticker_map = ec.fetch_ticker_map(ttl_seconds=self._ttl)
        return self._ticker_map

    def _first_available(
        self, facts: dict, candidates, as_of_iso: str
    ):
        """Try each (ns, tag, unit, annual_only) in order; return first hit."""
        from . import _edgar_client as ec
        for ns, tag, unit, annual in candidates:
            point = ec.latest_as_of(
                facts, namespace=ns, tag=tag, unit=unit,
                as_of=as_of_iso, annual_only=annual,
            )
            if point is not None:
                return point
        return None

    def fetch_as_of(
        self, tickers: list[str], *, as_of: date, model: str
    ) -> PitResult:
        from . import _edgar_client as ec

        as_of_iso = as_of.isoformat()
        ticker_map = self._ensure_map()
        rows: list[dict[str, Any]] = []
        warnings: list[str] = []

        for ticker_raw in tickers:
            ticker = ticker_raw.upper()
            row: dict[str, Any] = {
                "ticker": ticker_raw,
                "name": None,
                "vol_avg_3m": None,
                "target_return": None,
                "analyst_sent": None,
                "altman_z": None,
                "dvd_yld_ind": None,
            }
            cik = ticker_map.get(ticker)
            if cik is None:
                row["_edgar_error"] = "cik_not_found"
                rows.append(row)
                continue
            try:
                facts = ec.fetch_companyfacts(cik, ttl_seconds=self._ttl)
            except ec.EdgarError as e:
                row["_edgar_error"] = f"fetch_failed: {e}"
                rows.append(row)
                continue

            row["name"] = facts.get("entityName")

            # --- Altman-Z' components ----------------------------------
            ta = self._first_available(facts, self._TAGS_TOTAL_ASSETS, as_of_iso)
            liab = self._first_available(facts, self._TAGS_LIABILITIES, as_of_iso)
            ca = self._first_available(facts, self._TAGS_CURRENT_ASSETS, as_of_iso)
            cl = self._first_available(facts, self._TAGS_CURRENT_LIAB, as_of_iso)
            re_pt = self._first_available(facts, self._TAGS_RETAINED, as_of_iso)
            ebit = self._first_available(facts, self._TAGS_EBIT, as_of_iso)
            rev = self._first_available(facts, self._TAGS_REVENUE, as_of_iso)
            eq = self._first_available(facts, self._TAGS_EQUITY, as_of_iso)

            if all(p is not None for p in (ta, liab, ca, cl, re_pt, ebit, rev, eq)) and ta.val > 0 and liab.val > 0:
                wc = ca.val - cl.val
                z_prime = (
                    0.717 * (wc / ta.val)
                    + 0.847 * (re_pt.val / ta.val)
                    + 3.107 * (ebit.val / ta.val)
                    + 0.420 * (eq.val / liab.val)
                    + 0.998 * (rev.val / ta.val)
                )
                row["altman_z"] = round(z_prime, 3)

            # --- Annualized dividend yield -----------------------------
            # XBRL CommonStockDividendsPerShareDeclared in 10-Q is reported
            # YTD-cumulative (not stand-alone), so naive trailing-sum
            # double-counts. Cleanest approach: pull the most recent 10-K
            # FY value as the annualized DPS, divide by book-value-per-share.
            ttm_dvd = None
            for ns, tag, unit, _ in self._TAGS_DIVIDENDS_PS:
                pt = ec.latest_as_of(
                    facts, namespace=ns, tag=tag, unit=unit,
                    as_of=as_of_iso, annual_only=True,
                )
                if pt is not None:
                    ttm_dvd = pt.val
                    break
            shares = self._first_available(facts, self._TAGS_SHARES_OUT, as_of_iso)
            if ttm_dvd is not None and eq is not None and shares is not None and shares.val > 0:
                bvps = eq.val / shares.val
                if bvps > 0:
                    row["dvd_yld_ind"] = round(100.0 * ttm_dvd / bvps, 3)

            rows.append(row)

        warnings.append(
            f"edgar_pit: {sum(1 for r in rows if r.get('_edgar_error'))} of {len(rows)} "
            "tickers had no usable data (CIK not found or fetch failed)."
        )
        warnings.append(
            "edgar_pit: vol_avg_3m, target_return, and analyst_sent are NOT "
            "recoverable point-in-time from XBRL filings — those factors are "
            "left None and treated as missing by the scoring engine."
        )
        warnings.append(
            "edgar_pit: altman_z is computed as Altman Z' (private-firm "
            "variant) using book-value of equity, not market cap — avoids "
            "needing as-of price data."
        )
        warnings.append(
            "edgar_pit: dvd_yld_ind here is most-recent-10-K dividend per "
            "share / book-value per share — a BOOK yield, not market yield. "
            "Biased upward when buybacks compress book value (e.g. AAPL). "
            "Adding as-of price data would give a market yield; deferred."
        )

        return PitResult(
            rows=rows, as_of=as_of, provider=self.name, warnings=warnings,
        )


__all__ = ["PitProvider", "PitResult", "MockPitProvider", "EdgarPitProvider"]
