"""ThirteenFPitProvider — institutional positioning factor from 13F-HR.

For each ticker × as_of, this provider reports:

- ``inst_value_usd`` — total $ held by 13F filers in the most recently
  completed quarter
- ``inst_n_filers`` — number of distinct 13F filers reporting the ticker
- ``inst_concentration_score`` — 1-5 BOS score for "institutional
  concentration", calibrated for retail-vs-institutional positioning:
      1.0  fewer than 5 filers (orphan / micro)
      2.0  5–49 (low-coverage)
      3.0  50–249 (broad-mid)
      4.0  250–999 (consensus large-cap)
      5.0  1000+ (extreme institutional crowding — contrarian flag)

Extreme crowding (5+) is treated as a CAUTIOUS signal in this scale —
similar contrarian framing to retail_flow. A name held by every fund of
size is, by definition, no longer a hidden value play.

Limitations (documented openly, NOT bugs):
- One-quarter snapshot, not Δ-from-prior-quarter. Real institutional
  ALPHA signal is the change in concentration; absolute concentration
  is the framing here.
- CUSIP→ticker mapping is hand-curated; tickers without a CUSIP entry
  return None.
- 13F has a 45-day filing lag and the SEC bulk dataset publishes ~60
  days post-quarter. Effective lag: 60-90 days.
- Doesn't distinguish long-only positions from option overlays —
  13F-HR aggregates everything except long puts.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .cusip_map import cusip_for
from .pit import PitProvider, PitResult


def score_from_filer_count(n_filers: int) -> float:
    """Map institutional-filer count to the 1–5 BOS scale."""
    if n_filers >= 1000:
        return 5.0
    if n_filers >= 250:
        return 4.0
    if n_filers >= 50:
        return 3.0
    if n_filers >= 5:
        return 2.0
    return 1.0


class ThirteenFPitProvider(PitProvider):
    name = "thirteenf_pit"
    label = "SEC 13F-HR institutional aggregate"

    def __init__(self, *, ttl_seconds: int = 90 * 24 * 3600) -> None:
        self._ttl = ttl_seconds

    def fetch_as_of(
        self,
        tickers: list[str],
        *,
        as_of: date,
        model: str,
        prices: dict[str, dict[date, float]] | None = None,
        volumes: dict[str, dict[date, float]] | None = None,
    ) -> PitResult:
        del prices, volumes
        from . import _thirteenf_client as tf

        year, q = tf.latest_completed_quarter(as_of)
        warnings: list[str] = []
        try:
            aggregates = tf.fetch_13f_quarter(year, q, ttl_seconds=self._ttl)
        except tf.ThirteenFError as e:
            warnings.append(f"thirteenf_pit: bulk fetch failed: {e}")
            aggregates = {}

        rows: list[dict[str, Any]] = []
        unmapped: list[str] = []
        no_holdings: list[str] = []
        with_score = 0

        for ticker_raw in tickers:
            row: dict[str, Any] = {
                "ticker": ticker_raw,
                "name": None,
                # Other canonical factors stay None; this provider only emits
                # the institutional fields. Compose with MergedPitProvider.
                "vol_avg_3m": None, "target_return": None, "analyst_sent": None,
                "altman_z": None, "dvd_yld_ind": None, "insider_flow": None,
                "retail_flow": None,
                "inst_value_usd": None,
                "inst_n_filers": None,
                "inst_concentration_score": None,
            }
            cusip = cusip_for(ticker_raw)
            if cusip is None:
                unmapped.append(ticker_raw)
                rows.append(row)
                continue
            agg = aggregates.get(cusip)
            if agg is None:
                no_holdings.append(ticker_raw)
                rows.append(row)
                continue

            row["name"] = agg.issuer_name
            row["inst_value_usd"] = agg.total_value_usd
            row["inst_n_filers"] = agg.n_filers
            row["inst_concentration_score"] = score_from_filer_count(agg.n_filers)
            with_score += 1
            rows.append(row)

        warnings.insert(0,
            f"thirteenf_pit: institutional concentration for {with_score}/{len(rows)} "
            f"rows from {year}Q{q} 13F-HR aggregate."
        )
        if unmapped:
            warnings.append(
                f"thirteenf_pit: {len(unmapped)} tickers missing from "
                "TICKER_TO_CUSIP map (extend cusip_map.py): "
                + ", ".join(unmapped[:8])
                + ("..." if len(unmapped) > 8 else "")
            )
        if no_holdings:
            warnings.append(
                f"thirteenf_pit: {len(no_holdings)} tickers had no 13F holdings "
                f"in {year}Q{q} (or CUSIP not present in dataset)."
            )
        warnings.append(
            "thirteenf_pit: this provider returns ABSOLUTE concentration "
            "(filer count), not the period-over-period delta. Future work: "
            "fetch prior-quarter aggregate and emit Δ as a separate factor."
        )

        return PitResult(
            rows=rows, as_of=as_of, provider=self.name, warnings=warnings,
        )


__all__ = ["ThirteenFPitProvider", "score_from_filer_count"]
