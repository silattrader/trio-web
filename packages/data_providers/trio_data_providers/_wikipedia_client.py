"""Wikipedia pageviews client — Wikimedia REST API.

Daily pageview counts per article, all-access, all-agents. Free, no key.
History goes back to 2015-07-01. Data is finalised ~24h after midnight UTC,
so PIT-honesty for any `as_of` ≥ 1 day in the past is solid.

Endpoint:
  https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/
    en.wikipedia/all-access/all-agents/{article}/daily/{start}/{end}

User-Agent strongly encouraged (Wikimedia rate-limits anonymous traffic
aggressively). Set ``TRIO_WIKI_UA`` or it falls back to a project-identifying
default.

Cache lives at ``~/.trio_cache/wikipedia/``. Per-(article, year) cached
once and shared across as_of queries — much cheaper than re-fetching ranges.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import requests

DEFAULT_UA = "TRIO-Web Research silattrader@gmail.com"
PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/all-agents/{article}/daily/{start}/{end}"
)
CACHE_DIR = Path(os.environ.get(
    "TRIO_WIKI_CACHE", str(Path.home() / ".trio_cache" / "wikipedia")
))
DEFAULT_TTL_SECONDS = 7 * 24 * 3600  # weekly refresh — pageview data is final


class WikiError(RuntimeError):
    pass


def _ua() -> str:
    return os.environ.get("TRIO_WIKI_UA", DEFAULT_UA)


def _headers() -> dict[str, str]:
    return {
        "User-Agent": _ua(),
        "Accept": "application/json",
        "Api-User-Agent": _ua(),
    }


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


def _yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def fetch_daily_pageviews(
    article: str, *, start: date, end: date,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[date, int]:
    """Returns {date: views} for the article in [start, end]. Cached."""
    safe = urllib.parse.quote(article.replace(" ", "_"), safe="")
    cache = _cache_path(f"{safe}_{_yyyymmdd(start)}_{_yyyymmdd(end)}.json")

    if cache.exists() and (time.time() - cache.stat().st_mtime) <= ttl_seconds:
        try:
            raw = json.loads(cache.read_text(encoding="utf-8"))
            return {date.fromisoformat(k): int(v) for k, v in raw.items()}
        except (OSError, ValueError):
            pass

    url = PAGEVIEWS_URL.format(
        article=safe, start=_yyyymmdd(start), end=_yyyymmdd(end),
    )
    try:
        r = requests.get(url, headers=_headers(), timeout=30)
    except requests.RequestException as e:
        raise WikiError(f"GET {url}: {e}") from e
    if r.status_code == 404:
        # Article doesn't exist or no data for this range.
        return {}
    if r.status_code >= 400:
        raise WikiError(f"GET {url}: {r.status_code}")
    try:
        data = r.json()
    except ValueError as e:
        raise WikiError(f"GET {url}: invalid JSON: {e}") from e

    out: dict[date, int] = {}
    for item in data.get("items", []):
        ts = item.get("timestamp", "")
        # Format YYYYMMDDHH; strip the hour.
        if len(ts) >= 8:
            try:
                d = date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))
                out[d] = int(item.get("views", 0))
            except (ValueError, TypeError):
                continue
    try:
        cache.write_text(
            json.dumps({d.isoformat(): v for d, v in out.items()}),
            encoding="utf-8",
        )
    except OSError:
        pass
    return out


def fetch_pageviews_window(
    article: str, *, as_of: date, lookback_days: int = 365,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[date, int]:
    """Pull pageviews for the trailing `lookback_days` ending at `as_of`."""
    start = as_of - timedelta(days=lookback_days)
    return fetch_daily_pageviews(
        article, start=start, end=as_of, ttl_seconds=ttl_seconds,
    )


__all__ = [
    "WikiError",
    "fetch_daily_pageviews",
    "fetch_pageviews_window",
]
