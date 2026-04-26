"""Build a real PIT training dataset from EDGAR + yfinance.

For each (ticker, snapshot_date) we collect:
- Features: the 4-of-5 BOS factors that are PIT-honest (vol_avg_3m,
  dvd_yld_ind market-yield, altman_z, plus we synthesise a placeholder
  for analyst_sent because forward-looking data isn't in XBRL).
- Label: forward N-day return (close[t + N] / close[t] - 1), where N
  defaults to 63 trading days (~3 months).

This replaces the synthetic-only training loop in ``train.py`` with real
historical data. Output is cached to disk so subsequent training runs
don't refetch.

Notes:
- Network-heavy. ~1 EDGAR fetch per ticker (cached forever in
  ``~/.trio_cache/edgar/``) + 1 yfinance call per ticker for the full
  history range.
- target_return + analyst_sent stay None at PIT — we substitute the
  `forward_return_lookahead_proxy` median for analyst_sent (a known
  weak proxy) and 0 for target_return so the model has 5 columns. Both
  are flagged as synthetic in the dataset's `note` column.
- Snapshot dates default to quarter-end; one row per ticker per quarter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np


@dataclass
class PitSample:
    ticker: str
    as_of: date
    features: dict[str, float | None]
    forward_return: float | None  # label (None if can't be computed)
    note: str = ""


# Curated US large-cap universe with long XBRL history. Avoids banks (Z'
# returns None for them — fine for production, but training wants signal).
DEFAULT_UNIVERSE = [
    # Tech
    "AAPL", "MSFT", "GOOGL", "META", "NVDA", "ORCL", "CRM", "ADBE",
    # Consumer
    "AMZN", "WMT", "COST", "MCD", "KO", "PEP", "PG", "NKE",
    # Industrials / Energy
    "BA", "CAT", "DE", "HON", "XOM", "CVX",
    # Healthcare
    "JNJ", "PFE", "MRK", "ABBV", "LLY", "UNH",
]


def quarter_ends(start: date, end: date) -> list[date]:
    """Return calendar quarter-end dates between [start, end]."""
    out = []
    y, m = start.year, ((start.month - 1) // 3 + 1) * 3
    while True:
        # Calendar quarter-end month: 3, 6, 9, 12 → last day of that month.
        if m == 12:
            d = date(y, 12, 31)
        elif m == 9:
            d = date(y, 9, 30)
        elif m == 6:
            d = date(y, 6, 30)
        else:
            d = date(y, 3, 31)
        if d > end:
            break
        if d >= start:
            out.append(d)
        m += 3
        if m > 12:
            m = 3
            y += 1
    return out


def _forward_return(
    history: dict[date, float], start_date: date, n_trading_days: int = 63
) -> float | None:
    """Close[start + N trading days] / Close[start] - 1. Forward-fill on
    `start` if exact-date close is missing."""
    if not history:
        return None
    # Forward-fill start price.
    sorted_dates = sorted(history.keys())
    start_price = None
    for d in sorted_dates:
        if d <= start_date and history[d] > 0:
            start_price = history[d]
            start_d_idx = sorted_dates.index(d)
        if d > start_date:
            break
    if start_price is None:
        return None
    # Find the date roughly N trading days later.
    target_idx = start_d_idx + n_trading_days  # approximate trading-day count
    if target_idx >= len(sorted_dates):
        return None
    end_price = history[sorted_dates[target_idx]]
    if end_price <= 0:
        return None
    return float(end_price / start_price - 1)


def build_pit_dataset(
    *,
    universe: list[str] | None = None,
    start: date = date(2018, 3, 31),
    end: date = date(2023, 12, 31),
    forward_days: int = 63,
    cache_path: Path | None = None,
) -> list[PitSample]:
    """Materialise a PIT dataset. Caches the resulting list to ``cache_path``.

    Network-heavy on first run; instant on subsequent calls when cached.
    """
    if cache_path is not None and cache_path.exists():
        import pickle
        try:
            return pickle.loads(cache_path.read_bytes())
        except Exception:  # noqa: BLE001
            pass  # fall through and rebuild

    universe = universe or DEFAULT_UNIVERSE
    snapshots = quarter_ends(start, end)

    # Pull prices + volumes once for the entire window. Push the start back
    # so forward returns at the latest snapshot are still computable.
    fetch_start = start - timedelta(days=30)
    fetch_end = end + timedelta(days=120)

    from trio_backtester.data import fetch_history, fetch_volume_history
    from trio_data_providers import (
        EdgarPitProvider,
        InsiderFlowPitProvider,
        MergedPitProvider,
        RetailFlowPitProvider,
    )

    _, prices = fetch_history(universe, fetch_start, fetch_end)
    volumes = fetch_volume_history(universe, fetch_start, fetch_end)
    # Compose: EDGAR (3 fundamental factors) + insider flow + retail flow.
    # FMP is intentionally excluded here — its free tier is too thin for a
    # multi-quarter walk over 28 tickers; placeholders fill target_return +
    # analyst_sent (matching inference time).
    edgar = EdgarPitProvider()
    pit = MergedPitProvider([
        edgar,
        InsiderFlowPitProvider(edgar_pit=edgar),
        RetailFlowPitProvider(),
    ])

    samples: list[PitSample] = []
    for as_of in snapshots:
        res = pit.fetch_as_of(
            universe, as_of=as_of, model="bos",
            prices=prices, volumes=volumes,
        )
        for row in res.rows:
            t = row["ticker"]
            forward = _forward_return(
                prices.get(t, {}), as_of, forward_days,
            )
            # 7 features. target_return + analyst_sent stay placeholders
            # unless an FMP-enabled pipeline supplies them. insider_flow +
            # retail_flow are real PIT scores from EDGAR Form 4 + Wikipedia.
            features = {
                "vol_avg_3m": row.get("vol_avg_3m"),
                "target_return": row.get("target_return") if row.get("target_return") is not None else 0.0,
                "dvd_yld_ind": row.get("dvd_yld_ind"),
                "altman_z": row.get("altman_z"),
                "analyst_sent": row.get("analyst_sent") if row.get("analyst_sent") is not None else 3.0,
                "insider_flow": row.get("insider_flow") if row.get("insider_flow") is not None else 3.0,
                "retail_flow": row.get("retail_flow") if row.get("retail_flow") is not None else 3.0,
            }
            samples.append(PitSample(
                ticker=t, as_of=as_of, features=features,
                forward_return=forward,
                note="target_return + analyst_sent placeholders unless FMP wired; insider/retail real PIT",
            ))

    if cache_path is not None:
        import pickle
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(pickle.dumps(samples))
    return samples


def to_xy(samples: list[PitSample]) -> tuple[np.ndarray, np.ndarray, list[PitSample]]:
    """Filter samples that have all needed features + label, then return arrays.

    Returns (X, y, kept_samples).
    """
    from .model import FEATURE_ORDER

    kept: list[PitSample] = []
    X_rows: list[list[float]] = []
    y_rows: list[float] = []
    for s in samples:
        if s.forward_return is None:
            continue
        feats = []
        ok = True
        for k in FEATURE_ORDER:
            v = s.features.get(k)
            if v is None:
                ok = False
                break
            try:
                feats.append(float(v))
            except (TypeError, ValueError):
                ok = False
                break
        if not ok:
            continue
        X_rows.append(feats)
        y_rows.append(s.forward_return)
        kept.append(s)
    if not X_rows:
        return np.zeros((0, len(FEATURE_ORDER))), np.zeros(0), []
    return np.asarray(X_rows, dtype=float), np.asarray(y_rows, dtype=float), kept


__all__ = [
    "DEFAULT_UNIVERSE",
    "PitSample",
    "build_pit_dataset",
    "quarter_ends",
    "to_xy",
]
