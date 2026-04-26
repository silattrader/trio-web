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
    """SEC EDGAR Companyfacts adapter (NOT YET IMPLEMENTED).

    Wire-up notes for the follow-up:
    - Endpoint: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
    - User-Agent header REQUIRED (set TRIO_SEC_UA env, e.g. "Mailto user@example.com")
    - CIK lookup via https://www.sec.gov/files/company_tickers.json
    - For each filing, read `start`/`end`/`filed` dates; pick the most recent
      facts whose `filed <= as_of` to avoid lookahead.
    - Altman-Z components: WorkingCapital, RetainedEarnings, EBIT, Liabilities,
      MarketCap (need price), Sales, TotalAssets — all in standard XBRL tags.
    - dvd_yld_ind: trailing 12-month CommonStockDividendsPerShareDeclared / price.
    - vol_avg_3m: not in EDGAR — pull from yfinance with as-of price slice.
    - target_return + analyst_sent: NOT recoverable point-in-time from filings.
      Fall back to today's snapshot and flag.

    Until implemented, this raises so callers fail loud rather than silently
    using synthetic data they thought was real.
    """

    name = "edgar_pit"
    label = "SEC EDGAR Companyfacts (point-in-time)"

    def fetch_as_of(
        self, tickers: list[str], *, as_of: date, model: str
    ) -> PitResult:
        raise NotImplementedError(
            "EdgarPitProvider is a documented stub — wire up SEC Companyfacts before use. "
            "See packages/data_providers/trio_data_providers/pit.py for the plan."
        )


__all__ = ["PitProvider", "PitResult", "MockPitProvider", "EdgarPitProvider"]
