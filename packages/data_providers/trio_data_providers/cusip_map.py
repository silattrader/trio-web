"""Hand-curated CUSIP ↔ ticker map for the curated US large-cap universe.

CUSIP licensing forbids redistribution of the full master file. We keep
just the CUSIPs we actually use — verified per-ticker against SEC EDGAR
filings (each 10-K cover page lists the issuer's CUSIP).

Extending this map is the only blocker to running 13F-aggregated
institutional flow on a new ticker. Process:

1. Find the issuer's most recent 10-K on SEC EDGAR.
2. The cover page lists the CUSIP for the registered class of common stock.
3. Add the entry below; the 13F provider picks it up immediately.

The 28-name basket below was assembled by reading 10-Ks. CUSIPs change on
corporate-action events (mergers, spin-offs); refresh annually.
"""
from __future__ import annotations

# 9-character standard CUSIP for the primary common-stock class.
TICKER_TO_CUSIP: dict[str, str] = {
    # Tech
    "AAPL":  "037833100",
    "MSFT":  "594918104",
    "GOOGL": "02079K305",
    "GOOG":  "02079K107",
    "META":  "30303M102",
    "NVDA":  "67066G104",
    "ORCL":  "68389X105",
    "CRM":   "79466L302",
    "ADBE":  "00724F101",
    # Consumer
    "AMZN":  "023135106",
    "WMT":   "931142103",
    "COST":  "22160K105",
    "MCD":   "580135101",
    "KO":    "191216100",
    "PEP":   "713448108",
    "PG":    "742718109",
    "NKE":   "654106103",
    # Industrials / Energy
    "BA":    "097023105",
    "CAT":   "149123101",
    "DE":    "244199105",
    "HON":   "438516106",
    "XOM":   "30231G102",
    "CVX":   "166764100",
    # Healthcare
    "JNJ":   "478160104",
    "PFE":   "717081103",
    "MRK":   "58933Y105",
    "ABBV":  "00287Y109",
    "LLY":   "532457108",
    "UNH":   "91324P102",
}


CUSIP_TO_TICKER: dict[str, str] = {c: t for t, c in TICKER_TO_CUSIP.items()}


def cusip_for(ticker: str) -> str | None:
    return TICKER_TO_CUSIP.get(ticker.upper())


def ticker_for(cusip: str) -> str | None:
    return CUSIP_TO_TICKER.get(cusip.upper())


__all__ = ["TICKER_TO_CUSIP", "CUSIP_TO_TICKER", "cusip_for", "ticker_for"]
