"""Price-history adapter. Thin wrapper around yfinance for backtests.

Tests inject `fetch_history` via dependency injection — the engine never imports
yfinance directly so unit tests stay offline.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol


class PriceHistory(Protocol):
    """date -> {ticker: adj_close}. Sorted ascending by date."""

    def __getitem__(self, key: date) -> dict[str, float]: ...
    def __iter__(self): ...
    def __len__(self) -> int: ...


def fetch_history(
    tickers: list[str], start: date, end: date
) -> tuple[list[date], dict[str, dict[date, float]]]:
    """Pull adjusted-close history for `tickers` between `start` and `end`.

    Returns (sorted_dates, {ticker: {date: close}}). Tickers that yfinance
    can't resolve are dropped silently — caller checks the returned ticker
    set against its request.
    """
    try:
        import yfinance as yf
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("yfinance not installed; install trio-backtester") from e

    raw = yf.download(
        tickers=" ".join(tickers),
        start=start.isoformat(),
        end=end.isoformat(),
        progress=False,
        auto_adjust=True,
        group_by="ticker",
        threads=False,
    )
    if raw is None or raw.empty:
        return [], {}

    out: dict[str, dict[date, float]] = {}
    all_dates: set[date] = set()

    if len(tickers) == 1:
        t = tickers[0]
        closes = raw["Close"] if "Close" in raw.columns else raw.get(("Close",))
        if closes is None:
            return [], {}
        d_map: dict[date, float] = {}
        for ts, val in closes.items():
            if val is None:
                continue
            d = ts.date() if hasattr(ts, "date") else ts
            d_map[d] = float(val)
            all_dates.add(d)
        out[t] = d_map
    else:
        for t in tickers:
            try:
                closes = raw[t]["Close"]
            except (KeyError, TypeError):
                continue
            d_map = {}
            for ts, val in closes.items():
                if val is None or (isinstance(val, float) and val != val):  # NaN
                    continue
                d = ts.date() if hasattr(ts, "date") else ts
                d_map[d] = float(val)
                all_dates.add(d)
            if d_map:
                out[t] = d_map

    return sorted(all_dates), out
