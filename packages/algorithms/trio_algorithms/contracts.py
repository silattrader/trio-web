"""Stable input/output contracts shared by RBA and MLA engines.

This contract MUST remain backwards-compatible across the RBA -> MLA upgrade.
The web layer codes against ScoreResponse only; it never sees engine internals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Recommendation(str, Enum):
    BUY_BUY = "BUY-BUY"
    BUY = "BUY"
    SELL = "SELL"
    SELL_SELL = "SELL-SELL"
    UNRANKED = "UNRANKED"


QUARTILE_TO_RECOMMENDATION: dict[int, Recommendation] = {
    1: Recommendation.BUY_BUY,
    2: Recommendation.BUY,
    3: Recommendation.SELL,
    4: Recommendation.SELL_SELL,
}


class FactorBreakdown(BaseModel):
    id: str
    label: str
    raw: float | None
    band: Literal["BUY", "NEUTRAL", "SELL", "N/A"]
    sub_score: float
    weight: float
    contribution: float
    flags: list[str] = Field(default_factory=list)


class StockResult(BaseModel):
    ticker: str
    name: str | None = None
    final_score: float | None
    quartile: int | None
    recommendation: Recommendation
    factors: list[FactorBreakdown]
    explanation: str | None = None
    flags: list[str] = Field(default_factory=list)


class BosWeights(BaseModel):
    """Per-factor weights for the BOS engine.

    Canonical defaults: F1=0.20, F2=0.20, F3=0.20, F4=0.30, F5=0.10.
    Sum is normalised to 1.0 before scoring; the UI can pass raw drag values.
    """

    model_config = ConfigDict(extra="forbid")

    f1_volume: float = Field(default=0.20, ge=0)
    f2_target: float = Field(default=0.20, ge=0)
    f3_dvd_yld: float = Field(default=0.20, ge=0)
    f4_altman_z: float = Field(default=0.30, ge=0)
    f5_analyst_sent: float = Field(default=0.10, ge=0)

    def normalised(self) -> "BosWeights":
        total = (
            self.f1_volume + self.f2_target + self.f3_dvd_yld
            + self.f4_altman_z + self.f5_analyst_sent
        )
        if total <= 0:
            return BosWeights()
        return BosWeights(
            f1_volume=self.f1_volume / total,
            f2_target=self.f2_target / total,
            f3_dvd_yld=self.f3_dvd_yld / total,
            f4_altman_z=self.f4_altman_z / total,
            f5_analyst_sent=self.f5_analyst_sent / total,
        )


class ScoreRequest(BaseModel):
    """Generic request — universe-agnostic. Each row is a dict of canonical fields."""

    model_config = ConfigDict(extra="forbid")

    universe: str = Field(default="CSV", description="KLCI | SP500 | CSV | <custom>")
    rows: list[dict[str, Any]]
    options: dict[str, Any] = Field(default_factory=dict)
    bos_weights: BosWeights | None = Field(
        default=None,
        description="Optional override for BOS factor weights. Ignored by MOS/4F.",
    )


class ScoreResponse(BaseModel):
    model_version: str
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    universe: str
    n_rows: int
    n_scored: int
    results: list[StockResult]
    warnings: list[str] = Field(default_factory=list)
