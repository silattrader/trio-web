"""SEC EDGAR XBRL Companyfacts client.

Low-level wrapper for two endpoints:
- https://www.sec.gov/files/company_tickers.json — CIK ↔ ticker map (~3 MB)
- https://data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json — all reported facts

SEC rules require a `User-Agent` header identifying the caller (mailto). Set
``TRIO_SEC_UA`` env var, e.g. ``"Mailto contact@example.com"``. A safe default
is provided so things don't break in tests but should be overridden in prod.

Disk cache lives at ``~/.trio_cache/edgar/`` — companyfacts JSON is large and
expensive to refetch. Stale-tolerance is 24h by default.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import requests

DEFAULT_UA = "TRIO-Web Research silattrader@gmail.com"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
CACHE_DIR = Path(os.environ.get("TRIO_EDGAR_CACHE", str(Path.home() / ".trio_cache" / "edgar")))
DEFAULT_TTL_SECONDS = 24 * 3600


class EdgarError(RuntimeError):
    """Network / parse failure talking to EDGAR."""


def _ua() -> str:
    return os.environ.get("TRIO_SEC_UA", DEFAULT_UA)


def _headers() -> dict[str, str]:
    return {"User-Agent": _ua(), "Accept": "application/json"}


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


def _read_cache(path: Path, ttl_seconds: int) -> dict | None:
    if not path.exists():
        return None
    if (time.time() - path.stat().st_mtime) > ttl_seconds:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_cache(path: Path, data: dict) -> None:
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass  # cache failure shouldn't break the request


def _get_json(url: str, *, timeout: float = 30.0) -> dict:
    try:
        r = requests.get(url, headers=_headers(), timeout=timeout)
    except requests.RequestException as e:
        raise EdgarError(f"GET {url}: {e}") from e
    if r.status_code == 404:
        raise EdgarError(f"GET {url}: 404 not found")
    if r.status_code >= 400:
        raise EdgarError(f"GET {url}: {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise EdgarError(f"GET {url}: invalid JSON: {e}") from e


def fetch_ticker_map(*, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict[str, str]:
    """Returns {ticker_upper: cik_padded_to_10}."""
    cached = _read_cache(_cache_path("ticker_map.json"), ttl_seconds)
    if cached is not None:
        return cached

    raw = _get_json(TICKERS_URL)
    # Schema: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "..."}, ...}
    out: dict[str, str] = {}
    for entry in raw.values():
        ticker = str(entry.get("ticker", "")).upper()
        cik = entry.get("cik_str")
        if ticker and cik is not None:
            out[ticker] = str(cik).zfill(10)
    _write_cache(_cache_path("ticker_map.json"), out)
    return out


def fetch_companyfacts(cik: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict:
    """Pull the full XBRL facts blob for one CIK. Cached aggressively."""
    cik_padded = cik.zfill(10)
    cache = _cache_path(f"facts_{cik_padded}.json")
    cached = _read_cache(cache, ttl_seconds)
    if cached is not None:
        return cached
    raw = _get_json(COMPANYFACTS_URL.format(cik=cik_padded))
    _write_cache(cache, raw)
    return raw


# --------------------------------------------------------------------------
# Fact extraction — pick the most-recent reported value with filed <= as_of
# --------------------------------------------------------------------------


@dataclass
class FactPoint:
    val: float
    end: str   # ISO date — fact's reporting-period end
    filed: str  # ISO date — when filing was made public
    form: str   # 10-K / 10-Q / etc.
    fy: int | None
    fp: str | None  # FY / Q1 / Q2 / Q3


def _extract_unit_series(
    facts: dict, namespace: str, tag: str, unit: str
) -> list[FactPoint]:
    series = (
        facts.get("facts", {}).get(namespace, {}).get(tag, {}).get("units", {}).get(unit, [])
    )
    out: list[FactPoint] = []
    for entry in series:
        try:
            out.append(FactPoint(
                val=float(entry["val"]),
                end=entry["end"],
                filed=entry["filed"],
                form=entry.get("form", ""),
                fy=entry.get("fy"),
                fp=entry.get("fp"),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def latest_as_of(
    facts: dict,
    *,
    namespace: str,
    tag: str,
    unit: str,
    as_of: str,
    annual_only: bool = False,
) -> FactPoint | None:
    """Most recent fact whose ``filed`` is <= ``as_of`` (ISO YYYY-MM-DD).

    When ``annual_only`` is set, only 10-K / 20-F filings are considered —
    useful for balance-sheet items where mixing 10-Q and 10-K can be noisy.
    """
    series = _extract_unit_series(facts, namespace, tag, unit)
    if annual_only:
        series = [s for s in series if s.form in {"10-K", "10-K/A", "20-F", "20-F/A"}]
    valid = [s for s in series if s.filed <= as_of]
    if not valid:
        return None
    # Most recent by `end` date — that's the latest reporting-period covered.
    valid.sort(key=lambda s: (s.end, s.filed))
    return valid[-1]


def latest_max_at_end(
    facts: dict,
    *,
    namespace: str,
    tag: str,
    unit: str,
    as_of: str,
    annual_only: bool = False,
) -> FactPoint | None:
    """At the most recent ``end`` visible at ``as_of``, return the row with
    the LARGEST val. Useful for concepts where XBRL stores both quarterly
    and full-year rows under the same end-date (e.g. dividends-per-share)
    and we want the annual figure."""
    series = _extract_unit_series(facts, namespace, tag, unit)
    if annual_only:
        series = [s for s in series if s.form in {"10-K", "10-K/A", "20-F", "20-F/A"}]
    visible = [s for s in series if s.filed <= as_of]
    if not visible:
        return None
    # Find the most recent end-date.
    last_end = max(s.end for s in visible)
    candidates = [s for s in visible if s.end == last_end]
    candidates.sort(key=lambda s: s.val, reverse=True)
    return candidates[0]


def trailing_sum(
    facts: dict,
    *,
    namespace: str,
    tag: str,
    unit: str,
    as_of: str,
    days: int = 365,
    quarterly_only: bool = True,
) -> float | None:
    """Sum of fact values over ~the last `days` ending at the most recent
    period-end visible at as_of.

    XBRL reports the same concept (e.g. dividends-per-share) at multiple
    granularities: 10-Q gives quarterly figures, 10-K gives the full-year
    sum. Naive summing double-counts. ``quarterly_only`` keeps only fp ∈
    {Q1, Q2, Q3, Q4} so a 4-quarter sum truly equals trailing 12 months.
    """
    from datetime import date

    series = _extract_unit_series(facts, namespace, tag, unit)
    series = [s for s in series if s.filed <= as_of]
    if quarterly_only:
        series = [s for s in series if s.fp in {"Q1", "Q2", "Q3", "Q4"}]
    if not series:
        return None
    series.sort(key=lambda s: s.end)
    last_end = date.fromisoformat(series[-1].end)
    cutoff = last_end.toordinal() - days
    selected = [s for s in series if date.fromisoformat(s.end).toordinal() > cutoff]
    if not selected:
        return None
    # De-dup by `end` only — XBRL re-reports prior periods in subsequent
    # filings for comparison; (end, fy, fp) doesn't catch all duplicates
    # because comparison tags drift. Keeping the first-seen (which is the
    # earliest-filed for that period) is fine for a sum.
    seen: set[str] = set()
    total = 0.0
    for s in selected:
        if s.end in seen:
            continue
        seen.add(s.end)
        total += s.val
    return total


__all__ = [
    "EdgarError",
    "FactPoint",
    "fetch_companyfacts",
    "fetch_ticker_map",
    "latest_as_of",
    "latest_max_at_end",
    "trailing_sum",
]
