"""Bloomberg adapter — STUB.

Bloomberg has the cleanest BOS / MOS field coverage (the legacy POC was built
against Bloomberg CSV exports). We keep a structural stub so the registry
exposes it consistently in `/providers`, but no live calls happen until
credentials are supplied.

To activate (P3+ work):
  1. Acquire Bloomberg API access — typically blpapi via a Terminal session,
     a B-PIPE connection, or the Bloomberg Open API on a sponsored host.
  2. Set the following env vars before booting the API:
       TRIO_BLOOMBERG_HOST=localhost           # or B-PIPE host
       TRIO_BLOOMBERG_PORT=8194                # default
       TRIO_BLOOMBERG_AUTH=<auth string>       # if required
  3. Replace the body of `fetch` with a `blpapi.Session` call (HistoricalDataRequest
     for VOLUME_AVG_3M / EQY_DVD_YLD_IND, ReferenceDataRequest for ALTMAN_Z_SCORE,
     EQY_REC_CONS, RETURN, balance-sheet rows for MOS).

Until then, calling fetch() raises ProviderError.
"""
from __future__ import annotations

import os

from .base import DataProvider, ProviderError, ProviderResult

REQUIRED_ENV = ("TRIO_BLOOMBERG_HOST", "TRIO_BLOOMBERG_PORT")

BLOOMBERG_FIELDS_BOS = (
    "VOLUME_AVG_3M",
    "RETURN",
    "EQY_DVD_YLD_IND",
    "ALTMAN_Z_SCORE",
    "EQY_REC_CONS",
)


class BloombergProvider(DataProvider):
    name = "bloomberg"
    label = "Bloomberg — credentials required (stub)"

    def coverage(self, model: str) -> set[str]:
        if model == "bos":
            return {"vol_avg_3m", "target_return", "dvd_yld_ind", "altman_z", "analyst_sent"}
        if model == "mos":
            return {
                "cash_near_cash", "accounts_receivable", "inventories", "other_current_assets",
                "accounts_payable", "other_st_liab", "st_borrow", "non_current_liab",
                "shares_out", "px_last", "best_target_price",
            }
        if model == "four_factor":
            return {"altman_z", "dvd_yld_est", "roe_3yr_avg", "pe_ratio", "pe_5yr_avg"}
        return set()

    def fetch(self, tickers: list[str], *, model: str) -> ProviderResult:
        missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
        if missing:
            raise ProviderError(
                "Bloomberg provider not configured. Missing env vars: "
                + ", ".join(missing)
                + ". See packages/data_providers/trio_data_providers/bloomberg_provider.py "
                  "for activation steps."
            )
        # Hook for the future blpapi implementation.
        raise ProviderError(
            "Bloomberg adapter is a stub. blpapi integration pending — "
            "implement `fetch()` once credentials and access are confirmed."
        )
