"""MergedPitProvider — combine multiple PitProviders into one row stream.

Each underlying provider populates the BOS factors it can recover PIT-honestly:

- EdgarPitProvider  → altman_z + dvd_yld_ind (with prices), vol_avg_3m (with volumes)
- FmpPitProvider    → target_return + analyst_sent

Merging by ticker yields the full 5-of-5 BOS factor set without lookahead.
Last-non-None-wins: each provider's None values are preserved unless a later
provider in the chain fills them. Order matters — put your highest-quality
provider first.

Warnings from all underlying providers are concatenated and prefixed with
the provider name so it's clear which factor came from where.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .pit import PitProvider, PitResult


class MergedPitProvider(PitProvider):
    name = "merged_pit"

    def __init__(self, providers: list[PitProvider]) -> None:
        if not providers:
            raise ValueError("MergedPitProvider needs at least one provider")
        self._providers = providers
        self.label = (
            "Merged: " + " + ".join(p.name for p in providers)
        )

    def fetch_as_of(
        self,
        tickers: list[str],
        *,
        as_of: date,
        model: str,
        prices: dict[str, dict[date, float]] | None = None,
        volumes: dict[str, dict[date, float]] | None = None,
    ) -> PitResult:
        # First provider establishes the row order; later providers fill gaps.
        accumulator: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        for provider in self._providers:
            sub = provider.fetch_as_of(
                tickers, as_of=as_of, model=model,
                prices=prices, volumes=volumes,
            )
            for w in sub.warnings:
                warnings.append(f"[{provider.name}] {w}")
            for row in sub.rows:
                ticker = row.get("ticker")
                if ticker is None:
                    continue
                existing = accumulator.setdefault(ticker, {"ticker": ticker})
                for k, v in row.items():
                    if k == "ticker":
                        continue
                    # Last-non-None-wins: only overwrite if existing slot is None,
                    # except for diagnostic "_*" keys which always overlay.
                    if k.startswith("_"):
                        existing[k] = v
                    elif existing.get(k) is None:
                        existing[k] = v

        # Preserve original ticker order from the first call.
        first = self._providers[0].fetch_as_of(
            tickers, as_of=as_of, model=model,
            prices=prices, volumes=volumes,
        )
        # ^ already cached by the providers themselves; cheap.
        ordered_tickers = [r["ticker"] for r in first.rows if "ticker" in r]
        rows = [accumulator[t] for t in ordered_tickers if t in accumulator]

        # Coverage summary — what fraction of rows got each factor populated.
        n = len(rows) or 1
        cov = {
            k: sum(1 for r in rows if r.get(k) is not None) / n
            for k in ("vol_avg_3m", "target_return", "dvd_yld_ind",
                      "altman_z", "analyst_sent")
        }
        warnings.insert(0, "merged_pit factor coverage: " + ", ".join(
            f"{k}={int(v*100)}%" for k, v in cov.items()
        ))

        return PitResult(
            rows=rows, as_of=as_of, provider=self.name, warnings=warnings,
        )


__all__ = ["MergedPitProvider"]
