"""InsiderFlowPitProvider — institutional/insider-flow factor for BOS-Flow.

Uses SEC Form 4 filings (already cached via `_edgar_form4`) to build an
``insider_flow`` field on the canonical row. The factor captures the net
dollar flow of insider buying minus selling over a trailing window,
normalised by daily average dollar volume so it's comparable across tickers
with different market caps.

Score scale: same convention as the existing BOS factors (1–5, where 5 =
strong BUY signal).

Logic:
1. Pull Form 4 transactions filed in (as_of − lookback_days, as_of] for
   each ticker (CIK lookup uses the cached map from EdgarPitProvider).
2. Sum signed dollar value of non-derivative transactions
   (acquired = +shares*price, disposed = −shares*price).
3. Normalise: net_dollar / avg_daily_dollar_volume (gives "days of volume
   absorbed"). A typical "informative" insider buy is +0.05–0.50 days;
   strong selling pressure can be −0.5 to −5+ days.
4. Map to 1–5 with thresholds tuned for daily-volume-normalised flow.
   Empirically (per smoke tests on AAPL/MSFT/TSLA/NVDA/JNJ in 2023),
   insider activity for mega-caps lands in ±0.01 of daily $-volume; only
   small/mid-caps see ±0.05+:
       net/dvol  ≥ +0.025  → 5.0  (heavy insider buying)
       ≥ +0.005           → 4.0
       between ±0.005     → 3.0  (neutral)
       ≥ -0.025           → 2.0
       <  -0.025          → 1.0  (heavy insider selling)

This provider only fills ``insider_flow``. Other BOS factors stay None;
compose with EDGAR / FMP / yfinance via `MergedPitProvider` for full
coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .pit import EdgarPitProvider, PitProvider, PitResult


@dataclass
class _InsiderStats:
    n_transactions: int = 0
    n_buys: int = 0
    n_sells: int = 0
    net_usd: float = 0.0
    gross_buy_usd: float = 0.0
    gross_sell_usd: float = 0.0


def score_from_normalised_flow(net_per_dvol: float) -> float:
    """Map normalised net flow to a 1–5 BOS-style band. Thresholds tuned
    against empirical mega-cap insider activity — see module docstring."""
    if net_per_dvol >= 0.025:
        return 5.0
    if net_per_dvol >= 0.005:
        return 4.0
    if net_per_dvol >= -0.005:
        return 3.0
    if net_per_dvol >= -0.025:
        return 2.0
    return 1.0


class InsiderFlowPitProvider(PitProvider):
    name = "insider_flow_pit"
    label = "SEC Form 4 insider net buying"

    def __init__(
        self,
        *,
        ttl_seconds: int = 24 * 3600,
        lookback_days: int = 90,
        # CIK lookup is shared with EdgarPitProvider — re-using the cached map
        # avoids duplicate downloads of company_tickers.json.
        edgar_pit: EdgarPitProvider | None = None,
    ) -> None:
        self._ttl = ttl_seconds
        self._lookback = lookback_days
        self._edgar = edgar_pit or EdgarPitProvider(ttl_seconds=ttl_seconds)

    def _stats_for(self, cik: str, as_of: date) -> _InsiderStats:
        from . import _edgar_form4 as f4
        try:
            txs = f4.collect_insider_transactions(
                cik, as_of=as_of, lookback_days=self._lookback,
                ttl_seconds=self._ttl,
            )
        except f4.Form4Error:
            return _InsiderStats()

        st = _InsiderStats()
        for t in txs:
            # Only open-market purchases/sales carry signal — drop RSU vests
            # (M), grants (A), gifts (G), tax-withholding sales (F), etc.
            if not t.is_discretionary:
                continue
            st.n_transactions += 1
            if t.acquired:
                st.n_buys += 1
                st.gross_buy_usd += t.shares * t.price
            else:
                st.n_sells += 1
                st.gross_sell_usd += t.shares * t.price
            st.net_usd += t.signed_value_usd
        return st

    @staticmethod
    def _avg_daily_dvol(
        prices: dict[date, float] | None,
        volumes: dict[date, float] | None,
        as_of: date,
        n_bars: int = 63,
    ) -> float | None:
        """Mean of (price × volume) over the trailing ~3 months."""
        if not prices or not volumes:
            return None
        dates = sorted(d for d in prices if d <= as_of and d in volumes)
        if not dates:
            return None
        window = dates[-n_bars:]
        if not window:
            return None
        total = sum(prices[d] * volumes[d] for d in window)
        return total / len(window)

    def fetch_as_of(
        self,
        tickers: list[str],
        *,
        as_of: date,
        model: str,
        prices: dict[str, dict[date, float]] | None = None,
        volumes: dict[str, dict[date, float]] | None = None,
    ) -> PitResult:
        ticker_map = self._edgar._ensure_map()
        rows: list[dict[str, Any]] = []
        with_flow = 0
        no_cik = 0

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
                "insider_flow": None,
            }
            cik = ticker_map.get(ticker)
            if cik is None:
                no_cik += 1
                rows.append(row)
                continue

            stats = self._stats_for(cik, as_of)
            row["_insider_n_transactions"] = stats.n_transactions
            row["_insider_n_buys"] = stats.n_buys
            row["_insider_n_sells"] = stats.n_sells
            row["_insider_net_usd"] = round(stats.net_usd, 2)

            if stats.n_transactions == 0:
                # Quiet → neutral, but flag it.
                row["insider_flow"] = 3.0
                row["_insider_score_kind"] = "neutral_quiet"
                rows.append(row)
                continue

            # Need average daily dollar volume to normalise.
            dvol = self._avg_daily_dvol(
                prices.get(ticker_raw) or prices.get(ticker) if prices else None,
                volumes.get(ticker_raw) or volumes.get(ticker) if volumes else None,
                as_of,
            )
            if dvol is None or dvol <= 0:
                # Can't normalise → fall back on sign-only scoring.
                row["insider_flow"] = (
                    4.0 if stats.net_usd > 0 else
                    2.0 if stats.net_usd < 0 else 3.0
                )
                row["_insider_score_kind"] = "sign_only_fallback"
                with_flow += 1
                rows.append(row)
                continue

            normalised = stats.net_usd / dvol
            row["_insider_net_per_dvol"] = round(normalised, 4)
            row["insider_flow"] = score_from_normalised_flow(normalised)
            row["_insider_score_kind"] = "normalised"
            with_flow += 1
            rows.append(row)

        warnings = [
            f"insider_flow_pit: insider_flow populated for {with_flow}/{len(rows)} "
            f"rows over trailing {self._lookback}d (Form 4 net buy/sell ÷ "
            "63-day mean dollar volume).",
        ]
        if no_cik:
            warnings.append(
                f"insider_flow_pit: {no_cik} tickers had no CIK match (US-only)."
            )
        if prices is None or volumes is None:
            warnings.append(
                "insider_flow_pit: prices=/volumes= not supplied — falling back "
                "to sign-only scoring (4=net buy / 2=net sell), no magnitude."
            )

        return PitResult(
            rows=rows, as_of=as_of, provider=self.name, warnings=warnings,
        )


__all__ = ["InsiderFlowPitProvider", "score_from_normalised_flow"]
