"""FmpPitProvider — point-in-time analyst data via Financial Modeling Prep.

Fills the two BOS factors EDGAR cannot supply:
- ``target_return`` — (consensus_target_price − current_price) / current_price * 100
- ``analyst_sent`` — mean of recent rating changes mapped to a 1-5 scale
  (5 = strongest BUY, 1 = strongest SELL)

By itself this provider returns rows with vol_avg_3m / dvd_yld_ind / altman_z
all None. Use ``MergedPitProvider`` to combine with EdgarPitProvider for the
full 5-of-5 BOS factor coverage.

Honesty notes:
- FMP free tier may cap historical depth on these endpoints, so PIT
  reconstruction can be sparse for older `as_of` dates. Each row carries
  a ``_fmp_note`` field summarising what was found.
- Rating taxonomy varies across firms. The mapping in ``GRADE_TO_SCORE``
  is hand-crafted and conservative; unrecognised grades default to 3
  (neutral) and are flagged.
- Consensus target = simple mean of all targets within the trailing window.
  Real consensus services use weighted/de-duplicated logic; this is the
  honest-but-naive version.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .pit import PitProvider, PitResult

# 1.0 (strong sell) → 5.0 (strong buy). BOS thresholds expect this scale.
# Lowercased on lookup to match FMP's varied casing.
GRADE_TO_SCORE: dict[str, float] = {
    # Strong buy / Buy variants
    "strong buy": 5.0,
    "buy": 4.5,
    "outperform": 4.5,
    "overweight": 4.5,
    "market outperform": 4.5,
    "sector outperform": 4.5,
    "positive": 4.5,
    "accumulate": 4.0,
    "add": 4.0,
    "long-term buy": 4.0,
    # Hold / Neutral
    "hold": 3.0,
    "neutral": 3.0,
    "market perform": 3.0,
    "sector perform": 3.0,
    "equal-weight": 3.0,
    "equal weight": 3.0,
    "in-line": 3.0,
    # Underperform / Sell
    "underperform": 2.0,
    "underweight": 2.0,
    "reduce": 2.0,
    "sector underperform": 2.0,
    "negative": 2.0,
    "sell": 1.5,
    "strong sell": 1.0,
}


@dataclass
class _AsOfStats:
    target_count: int = 0
    target_mean: float | None = None
    rating_count: int = 0
    rating_mean: float | None = None
    unmapped_grades: list[str] = field(default_factory=list)


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    # FMP often returns ISO datetime — split off the time portion if present.
    head = s.split("T", 1)[0].strip()
    try:
        return date.fromisoformat(head)
    except ValueError:
        return None


def _normalise_grade(g: str | None) -> float | None:
    if not g:
        return None
    return GRADE_TO_SCORE.get(g.lower().strip())


def _consensus_target(
    records: list[dict], *, as_of: date, window_days: int = 90
) -> tuple[float | None, int]:
    """Mean priceTarget across records published in [as_of − window_days, as_of]."""
    cutoff = as_of - timedelta(days=window_days)
    vals: list[float] = []
    for r in records:
        d = _parse_iso_date(r.get("publishedDate"))
        if d is None or d > as_of or d < cutoff:
            continue
        try:
            vals.append(float(r["priceTarget"]))
        except (KeyError, TypeError, ValueError):
            continue
    if not vals:
        return None, 0
    return sum(vals) / len(vals), len(vals)


def _consensus_rating(
    records: list[dict], *, as_of: date, window_days: int = 90,
) -> tuple[float | None, int, list[str]]:
    """Mean grade-score across rating changes in trailing window."""
    cutoff = as_of - timedelta(days=window_days)
    scores: list[float] = []
    unmapped: list[str] = []
    for r in records:
        d = _parse_iso_date(r.get("publishedDate"))
        if d is None or d > as_of or d < cutoff:
            continue
        new = r.get("newGrade")
        s = _normalise_grade(new)
        if s is None:
            if new and new not in unmapped:
                unmapped.append(str(new))
            continue
        scores.append(s)
    if not scores:
        return None, 0, unmapped
    return sum(scores) / len(scores), len(scores), unmapped


class FmpPitProvider(PitProvider):
    """Forward-looking analyst data via FMP. Set ``TRIO_FMP_KEY`` env first."""

    name = "fmp_pit"
    label = "Financial Modeling Prep (analyst PIT)"

    def __init__(self, *, ttl_seconds: int = 24 * 3600, window_days: int = 90) -> None:
        self._ttl = ttl_seconds
        self._window = window_days

    def _stats_for(self, ticker: str, as_of: date) -> _AsOfStats:
        from . import _fmp_client as fc
        st = _AsOfStats()
        try:
            targets = fc.fetch_price_targets(ticker, ttl_seconds=self._ttl)
        except fc.FmpError:
            targets = []
        try:
            ratings = fc.fetch_upgrades_downgrades(ticker, ttl_seconds=self._ttl)
        except fc.FmpError:
            ratings = []

        st.target_mean, st.target_count = _consensus_target(
            targets, as_of=as_of, window_days=self._window,
        )
        st.rating_mean, st.rating_count, st.unmapped_grades = _consensus_rating(
            ratings, as_of=as_of, window_days=self._window,
        )
        return st

    def fetch_as_of(
        self,
        tickers: list[str],
        *,
        as_of: date,
        model: str,
        prices: dict[str, dict[date, float]] | None = None,
        volumes: dict[str, dict[date, float]] | None = None,
    ) -> PitResult:
        del volumes  # FMP doesn't need volume data.
        rows: list[dict[str, Any]] = []
        unmapped_global: set[str] = set()
        with_target = with_sent = 0

        for ticker_raw in tickers:
            row: dict[str, Any] = {
                "ticker": ticker_raw,
                "name": None,
                "vol_avg_3m": None,
                "target_return": None,
                "analyst_sent": None,
                "altman_z": None,
                "dvd_yld_ind": None,
            }
            stats = self._stats_for(ticker_raw.upper(), as_of)

            # target_return = (consensus_target − current_price) / current_price * 100
            current_price = None
            if prices is not None:
                series = prices.get(ticker_raw) or prices.get(ticker_raw.upper())
                if series:
                    candidates = [d for d in series if d <= as_of]
                    if candidates:
                        current_price = series[max(candidates)]

            if stats.target_mean is not None and current_price and current_price > 0:
                row["target_return"] = round(
                    (stats.target_mean - current_price) / current_price * 100, 3,
                )
                with_target += 1

            if stats.rating_mean is not None:
                row["analyst_sent"] = round(stats.rating_mean, 3)
                with_sent += 1

            row["_fmp_targets"] = stats.target_count
            row["_fmp_ratings"] = stats.rating_count
            unmapped_global.update(stats.unmapped_grades)
            rows.append(row)

        warnings = [
            f"fmp_pit: target_return populated for {with_target}/{len(rows)} rows "
            "(consensus mean of analyst price targets in trailing 90d ÷ as-of price).",
            f"fmp_pit: analyst_sent populated for {with_sent}/{len(rows)} rows "
            "(mean of rating-change scores in trailing 90d, scale 1-5).",
        ]
        if prices is None:
            warnings.append(
                "fmp_pit: prices= not supplied — target_return cannot be computed "
                "without an as-of price; left None."
            )
        if unmapped_global:
            warnings.append(
                "fmp_pit: unrecognised analyst grades dropped (extend GRADE_TO_SCORE): "
                + ", ".join(sorted(unmapped_global)[:6])
                + ("..." if len(unmapped_global) > 6 else "")
            )
        warnings.append(
            "fmp_pit: free-tier coverage on /price-target and /upgrades-downgrades "
            "may cap older history — sparse for as_of dates pre-2022."
        )

        return PitResult(
            rows=rows, as_of=as_of, provider=self.name, warnings=warnings,
        )


__all__ = ["FmpPitProvider", "GRADE_TO_SCORE"]
