"""SEC EDGAR Form 4 client — insider transaction history.

Form 4 = "Statement of Changes in Beneficial Ownership". Insiders (officers,
directors, 10%+ owners) must file within 2 business days of any transaction
in their company's stock. Free, public, real-time-ish.

Two endpoints used:
- ``data.sec.gov/submissions/CIK{cik}.json`` → recent filings list per issuer.
  We filter to ``form == "4"`` and pick those whose ``filingDate <= as_of``.
- ``www.sec.gov/Archives/edgar/data/{cik}/{accNoNoDashes}/{primaryDocument}``
  → individual Form 4 XML. We parse non-derivative transactions.

Each transaction has:
- transactionDate
- transactionShares.value         (number of shares, always positive)
- transactionPricePerShare.value  (USD/share)
- transactionAcquiredDisposedCode.value  ('A' = acquired, 'D' = disposed)

Net dollar flow = Σ (A shares × price) - Σ (D shares × price) over a window.

Same User-Agent rules as the rest of EDGAR (set ``TRIO_SEC_UA``). Per-filing
XML is cached forever — Form 4s never change once filed.
"""
from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

from ._edgar_client import (
    DEFAULT_TTL_SECONDS,
    _read_cache,
    _write_cache,
    _ua,
)

CACHE_DIR = Path(os.environ.get("TRIO_FORM4_CACHE", str(Path.home() / ".trio_cache" / "form4")))
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FILING_BASE = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}"


class Form4Error(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    return {"User-Agent": _ua(), "Accept": "application/json"}


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


@dataclass
class InsiderTransaction:
    filing_accession: str
    filed: date
    transaction_date: date
    shares: float
    price: float
    acquired: bool   # True = 'A' (buy), False = 'D' (sell)
    code: str        # SEC transaction code: P=open-market buy, S=open-market sell, etc.
    title: str       # reporting owner relationship/title

    @property
    def signed_value_usd(self) -> float:
        v = self.shares * self.price
        return v if self.acquired else -v

    @property
    def is_discretionary(self) -> bool:
        """Open-market purchase or sale — the codes that carry signal.
        Excludes RSU vests (M), grants (A), gifts (G), tax-withholding (F)."""
        return self.code in {"P", "S"}


def fetch_recent_form4_index(
    cik: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS
) -> list[dict]:
    """Pull the issuer's recent-filings list, filter to Form 4 only.

    Returns a list of dicts with keys: accessionNumber, filingDate,
    primaryDocument, reportDate.
    """
    cik_padded = cik.zfill(10)
    cache = _cache_path(f"submissions_{cik_padded}.json")
    cached = _read_cache(cache, ttl_seconds)
    if cached is None:
        url = SUBMISSIONS_URL.format(cik=cik_padded)
        try:
            r = requests.get(url, headers=_headers(), timeout=30)
        except requests.RequestException as e:
            raise Form4Error(f"submissions fetch: {e}") from e
        if r.status_code >= 400:
            raise Form4Error(f"submissions {r.status_code}")
        try:
            cached = r.json()
        except ValueError as e:
            raise Form4Error(f"submissions parse: {e}") from e
        _write_cache(cache, cached)

    recent = cached.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accs = recent.get("accessionNumber", [])
    filed = recent.get("filingDate", [])
    reports = recent.get("reportDate", [])
    primaries = recent.get("primaryDocument", [])
    out: list[dict] = []
    for i, f in enumerate(forms):
        if f != "4":
            continue
        out.append({
            "accessionNumber": accs[i] if i < len(accs) else "",
            "filingDate": filed[i] if i < len(filed) else "",
            "reportDate": reports[i] if i < len(reports) else "",
            "primaryDocument": primaries[i] if i < len(primaries) else "",
        })
    return out


def _parse_iso(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find(elem: ET.Element, *path: str) -> ET.Element | None:
    """Walk a path of child tags ignoring namespaces."""
    for p in path:
        if elem is None:
            return None
        elem = next((c for c in elem if _strip_ns(c.tag) == p), None)
    return elem


def _find_value(elem: ET.Element | None, *path: str) -> str | None:
    target = _find(elem, *path) if elem is not None else None
    return target.text if target is not None else None


def fetch_form4_filing(
    cik: str, accession_no: str, primary_doc: str,
    *, ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Fetch + cache a single Form 4 raw XML. Returns the XML text.

    SEC's ``primaryDocument`` field often points at the XSL-rendered HTML
    wrapper (e.g. ``xslF345X04/wf-form4_xxx.xml``), not the raw XML. The
    raw XML lives at the same accession folder with the rendering prefix
    stripped — so we strip it before fetching.
    """
    acc_no_dashes = accession_no.replace("-", "")
    # Strip the SEC's rendering subfolder if present (e.g. xslF345X04/).
    raw_doc = primary_doc.split("/", 1)[1] if primary_doc.startswith("xsl") else primary_doc

    cache = _cache_path(f"form4_{acc_no_dashes}.xml")
    if cache.exists() and (time.time() - cache.stat().st_mtime) <= ttl_seconds:
        try:
            return cache.read_text(encoding="utf-8")
        except OSError:
            pass
    cik_int = str(int(cik))  # path uses the un-padded CIK
    url = FILING_BASE.format(cik_int=cik_int, acc=acc_no_dashes) + f"/{raw_doc}"
    try:
        r = requests.get(url, headers={"User-Agent": _ua()}, timeout=30)
    except requests.RequestException as e:
        raise Form4Error(f"filing fetch {accession_no}: {e}") from e
    if r.status_code >= 400:
        raise Form4Error(f"filing {accession_no} {r.status_code}")
    text = r.text
    try:
        cache.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return text


def parse_form4(xml_text: str, *, accession: str = "", filed: date | None = None) -> list[InsiderTransaction]:
    """Parse non-derivative transactions out of one Form 4 XML.

    Skips derivative transactions (options/RSUs) — those don't represent
    direct buy/sell pressure on the common stock.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # Reporting-owner title for context
    title_node = _find(root, "reportingOwner", "reportingOwnerRelationship")
    titles: list[str] = []
    if title_node is not None:
        for child in title_node:
            tag = _strip_ns(child.tag)
            if tag in {"isDirector", "isOfficer", "isTenPercentOwner", "isOther"} and (child.text or "").strip() in {"1", "true"}:
                titles.append(tag.replace("is", ""))
            elif tag == "officerTitle" and child.text:
                titles.append(child.text.strip())
    title = "/".join(titles) or "?"

    out: list[InsiderTransaction] = []
    nd_table = _find(root, "nonDerivativeTable")
    if nd_table is None:
        return out
    for tx in nd_table:
        if _strip_ns(tx.tag) != "nonDerivativeTransaction":
            continue
        tx_date_str = _find_value(tx, "transactionDate", "value")
        shares_str = _find_value(tx, "transactionAmounts", "transactionShares", "value")
        price_str = _find_value(tx, "transactionAmounts", "transactionPricePerShare", "value")
        ad_code = _find_value(tx, "transactionAmounts", "transactionAcquiredDisposedCode", "value")
        tx_code = _find_value(tx, "transactionCoding", "transactionCode") or ""

        tx_date = _parse_iso(tx_date_str or "")
        if tx_date is None:
            continue
        try:
            shares = float(shares_str or 0)
            price = float(price_str or 0)
        except ValueError:
            continue
        if shares == 0:
            continue
        acquired = (ad_code or "").upper() == "A"

        out.append(InsiderTransaction(
            filing_accession=accession,
            filed=filed or tx_date,
            transaction_date=tx_date,
            shares=shares,
            price=price,
            acquired=acquired,
            code=tx_code.strip().upper(),
            title=title,
        ))
    return out


def collect_insider_transactions(
    cik: str, *, as_of: date, lookback_days: int = 90,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> list[InsiderTransaction]:
    """End-to-end: pull Form 4 index, fetch+parse each filing whose
    ``filingDate`` falls in (as_of − lookback_days, as_of]."""
    from datetime import timedelta
    cutoff = as_of - timedelta(days=lookback_days)
    index = fetch_recent_form4_index(cik, ttl_seconds=ttl_seconds)
    transactions: list[InsiderTransaction] = []
    for entry in index:
        filed = _parse_iso(entry.get("filingDate", ""))
        if filed is None or filed > as_of or filed <= cutoff:
            continue
        try:
            xml_text = fetch_form4_filing(
                cik, entry["accessionNumber"], entry["primaryDocument"],
                ttl_seconds=ttl_seconds,
            )
        except Form4Error:
            continue
        transactions.extend(parse_form4(
            xml_text, accession=entry["accessionNumber"], filed=filed,
        ))
    return transactions


__all__ = [
    "Form4Error",
    "InsiderTransaction",
    "collect_insider_transactions",
    "fetch_form4_filing",
    "fetch_recent_form4_index",
    "parse_form4",
]
