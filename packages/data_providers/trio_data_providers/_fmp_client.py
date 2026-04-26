"""Financial Modeling Prep (FMP) HTTP client for forward-looking analyst data.

Two endpoints are useful for PIT analyst factors:
- /v3/price-target/{symbol}        — individual analyst price targets
- /v3/upgrades-downgrades/{symbol} — historical rating changes

Both return arrays with `publishedDate`, which is what we filter against to
enforce the no-lookahead invariant.

Auth: API key in the `apikey` query param. Set ``TRIO_FMP_KEY`` env. The
free tier (250 req/day, US stocks) is enough for a curated universe with
disk-cached responses — each ticker fetched once per `ttl_seconds`.

Free-tier caveat: FMP may cap the number of returned records on /price-target
and /upgrades-downgrades. If your `as_of` date is far in the past, the API
might return only recent records, leaving you with no PIT data. The provider
handles this gracefully (returns None) and emits a warning.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

DEFAULT_BASE = "https://financialmodelingprep.com/api/v3"
CACHE_DIR = Path(os.environ.get("TRIO_FMP_CACHE", str(Path.home() / ".trio_cache" / "fmp")))
DEFAULT_TTL_SECONDS = 24 * 3600


class FmpError(RuntimeError):
    """Network / parse / auth failure talking to FMP."""


def _key() -> str:
    from ._request_keys import request_fmp_key
    k = request_fmp_key()
    if not k:
        raise FmpError(
            "FMP key not set. Either set TRIO_FMP_KEY env, or paste a key "
            "in the Settings panel (BYOK mode). Get a free key at "
            "https://site.financialmodelingprep.com/developer/docs"
        )
    return k


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


def _read_cache(path: Path, ttl_seconds: int) -> list | dict | None:
    if not path.exists():
        return None
    if (time.time() - path.stat().st_mtime) > ttl_seconds:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_cache(path: Path, data) -> None:
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def _get_json(url: str, *, timeout: float = 30.0) -> list | dict:
    try:
        r = requests.get(url, timeout=timeout)
    except requests.RequestException as e:
        raise FmpError(f"GET {url}: {e}") from e
    if r.status_code == 401:
        raise FmpError("FMP returned 401 — check TRIO_FMP_KEY")
    if r.status_code == 429:
        raise FmpError("FMP returned 429 — daily/minute quota exceeded")
    if r.status_code >= 400:
        raise FmpError(f"GET {url}: {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise FmpError(f"GET {url}: invalid JSON: {e}") from e


def _fetch(endpoint: str, ticker: str, *, ttl_seconds: int) -> list:
    """Generic single-ticker fetch (price-target, upgrades-downgrades, ...)."""
    safe_ticker = ticker.replace("/", "_").upper()
    cache = _cache_path(f"{endpoint}_{safe_ticker}.json")
    cached = _read_cache(cache, ttl_seconds)
    if cached is not None:
        return cached if isinstance(cached, list) else []
    url = f"{DEFAULT_BASE}/{endpoint}/{safe_ticker}?apikey={_key()}"
    raw = _get_json(url)
    data = raw if isinstance(raw, list) else []
    _write_cache(cache, data)
    return data


def fetch_price_targets(
    ticker: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> list[dict]:
    """Return all analyst price-target records FMP gives us for `ticker`.

    Each record has at minimum:
        publishedDate (ISO date string)
        priceTarget    (float, USD)
        analystCompany (str)
    """
    return _fetch("price-target", ticker, ttl_seconds=ttl_seconds)


def fetch_upgrades_downgrades(
    ticker: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> list[dict]:
    """Return all rating-change records FMP gives us for `ticker`.

    Each record has at minimum:
        publishedDate  (ISO date string)
        newGrade       (str — "Buy", "Hold", "Sell", "Outperform", etc.)
        previousGrade  (str)
        gradingCompany (str)
        action         (str — "upgrade" / "downgrade" / "initiate" / etc.)
    """
    return _fetch("upgrades-downgrades", ticker, ttl_seconds=ttl_seconds)


__all__ = [
    "DEFAULT_BASE",
    "FmpError",
    "fetch_price_targets",
    "fetch_upgrades_downgrades",
]
