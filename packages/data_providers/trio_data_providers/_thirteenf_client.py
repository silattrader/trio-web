"""SEC 13F-HR bulk-dataset client.

The SEC publishes a structured quarterly dataset of every 13F-HR filing at
https://www.sec.gov/dera/data/form-13f.html. Each quarter is a ZIP of TSV
files; INFOTABLE.tsv holds every (filer, holding) row across the universe
of $100M+ institutional managers. Per-ticker aggregation across that file
gives you "total institutional ownership" point-in-time as of the quarter
end (with the standard 45-day filing-lag built in).

This client downloads + parses one quarter at a time and caches the parsed
result. The raw ZIP is ~50–200 MB; we throw it away after parsing because
the aggregated form is ~1 MB.

CUSIP→ticker resolution: 13F filings reference CUSIP, not ticker. There is
no free, comprehensive CUSIP→ticker map (CUSIP licensing). The provider
ships a hand-curated map for the curated US large-cap universe in
``cusip_map.py``; extend it to cover your tickers.

User-Agent rules: same as the rest of EDGAR; honour ``TRIO_SEC_UA``.
"""
from __future__ import annotations

import csv
import io
import json
import os
import time
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

CACHE_DIR = Path(os.environ.get(
    "TRIO_13F_CACHE", str(Path.home() / ".trio_cache" / "thirteen_f")
))
DEFAULT_TTL_SECONDS = 90 * 24 * 3600  # 90d — quarterly data, refreshed seldom

BULK_ZIP_URL_TMPL = (
    "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/"
    "{year}q{q}_form13f.zip"
)


class ThirteenFError(RuntimeError):
    pass


def _ua() -> str:
    from ._request_keys import request_sec_ua
    return request_sec_ua("TRIO-Web Research silattrader@gmail.com")


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


@dataclass(frozen=True)
class HoldingsAggregate:
    """Per-CUSIP roll-up of one quarter's 13F filings.

    All values are sums across every $100M+ filer that reported the security.
    """
    cusip: str
    issuer_name: str
    n_filers: int
    total_shares: int        # sum of SSHPRNAMT where TYPE=SH (sharecount)
    total_value_usd: float   # sum of VALUE * 1000 (the SEC reports thousands)


def _quarter_to_url(year: int, quarter: int) -> str:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1..4")
    return BULK_ZIP_URL_TMPL.format(year=year, q=quarter)


def fetch_13f_quarter(
    year: int, quarter: int,
    *, ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, HoldingsAggregate]:
    """Download, parse, and cache one quarter's 13F bulk dataset.

    Returns a {cusip: HoldingsAggregate} map. Cached as JSON so subsequent
    calls skip the (large) ZIP download.
    """
    label = f"{year}Q{quarter}"
    cache = _cache_path(f"agg_{label}.json")
    if cache.exists() and (time.time() - cache.stat().st_mtime) <= ttl_seconds:
        try:
            raw = json.loads(cache.read_text(encoding="utf-8"))
            return {
                cusip: HoldingsAggregate(**a) for cusip, a in raw.items()
            }
        except (OSError, ValueError):
            pass

    url = _quarter_to_url(year, quarter)
    try:
        r = requests.get(url, headers={"User-Agent": _ua()}, timeout=60)
    except requests.RequestException as e:
        raise ThirteenFError(f"GET {url}: {e}") from e
    if r.status_code == 404:
        raise ThirteenFError(
            f"13F bulk data for {label} not yet published. Quarterly drops "
            "land ~60 days after quarter-end."
        )
    if r.status_code >= 400:
        raise ThirteenFError(f"GET {url}: {r.status_code}")

    aggregates = parse_infotable_zip(r.content)
    cache.write_text(
        json.dumps({cusip: a.__dict__ for cusip, a in aggregates.items()}),
        encoding="utf-8",
    )
    return aggregates


def parse_infotable_zip(zip_bytes: bytes) -> dict[str, HoldingsAggregate]:
    """Extract INFOTABLE.tsv from the SEC bulk ZIP and aggregate by CUSIP."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        target = next(
            (n for n in zf.namelist() if n.upper().endswith("INFOTABLE.TSV")),
            None,
        )
        if target is None:
            raise ThirteenFError(
                "bulk ZIP did not contain INFOTABLE.tsv (SEC schema changed?)"
            )
        with zf.open(target) as f:
            text = io.TextIOWrapper(f, encoding="latin-1")
            return _aggregate_infotable(text)


def _aggregate_infotable(stream) -> dict[str, HoldingsAggregate]:
    """Parse INFOTABLE.tsv text stream and roll up per CUSIP."""
    reader = csv.DictReader(stream, delimiter="\t")
    rolled: dict[str, dict] = {}

    for row in reader:
        cusip = (row.get("CUSIP") or "").strip().upper()
        if not cusip:
            continue
        try:
            value_thousands = float(row.get("VALUE") or 0)
        except ValueError:
            continue
        try:
            shares = int(float(row.get("SSHPRNAMT") or 0))
        except ValueError:
            shares = 0
        sh_type = (row.get("SSHPRNAMTTYPE") or "").strip().upper()
        accn = (row.get("ACCESSION_NUMBER") or "").strip()
        issuer = (row.get("NAMEOFISSUER") or "").strip()

        bucket = rolled.setdefault(cusip, {
            "cusip": cusip, "issuer_name": issuer, "filers": set(),
            "total_shares": 0, "total_value_usd": 0.0,
        })
        bucket["filers"].add(accn)
        bucket["total_value_usd"] += value_thousands * 1000.0
        if sh_type == "SH":
            bucket["total_shares"] += shares
        # Keep first non-empty issuer name encountered.
        if issuer and not bucket["issuer_name"]:
            bucket["issuer_name"] = issuer

    return {
        cusip: HoldingsAggregate(
            cusip=cusip,
            issuer_name=b["issuer_name"],
            n_filers=len(b["filers"]),
            total_shares=b["total_shares"],
            total_value_usd=round(b["total_value_usd"], 2),
        )
        for cusip, b in rolled.items()
    }


def latest_completed_quarter(as_of: date) -> tuple[int, int]:
    """Most recent quarter whose 13F filings should be available given the
    ~45-day filing lag + ~15-day SEC data-set publication lag.

    Conservative rule: as of date D, return the quarter whose end is ≥ 60 days
    before D. Otherwise step back another quarter.
    """
    from datetime import timedelta
    cutoff = as_of - timedelta(days=60)
    for delta in range(0, 6):
        y = cutoff.year
        m = cutoff.month - delta * 3
        while m <= 0:
            m += 12
            y -= 1
        quarter = (m - 1) // 3 + 1
        # Quarter-end date
        qend_month = quarter * 3
        qend_day = {3: 31, 6: 30, 9: 30, 12: 31}[qend_month]
        qend = date(y, qend_month, qend_day)
        if qend <= cutoff:
            return y, quarter
    # Fallback: should never hit
    return as_of.year - 1, 4


__all__ = [
    "BULK_ZIP_URL_TMPL",
    "DEFAULT_TTL_SECONDS",
    "HoldingsAggregate",
    "ThirteenFError",
    "fetch_13f_quarter",
    "latest_completed_quarter",
    "parse_infotable_zip",
]
