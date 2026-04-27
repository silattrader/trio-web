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


class QvWeights(BaseModel):
    """Per-factor weights for the Quality-Value (QV) engine — 6 factors.

    Half quality / half value. Defaults reflect the empirical finding that
    Greenblatt's earnings yield and Novy-Marx's gross profitability are the
    strongest single-factor signals in their respective dimensions:

      Quality (50%):
        F1 roe                    0.15
        F2 gross_profit_to_assets 0.20  ← Novy-Marx (2013)
        F3 debt_to_equity         0.15  (lower = better — banding is reversed)

      Value (50%):
        F4 earnings_yield         0.20  ← Greenblatt Magic Formula (2006)
        F5 book_to_market         0.15  ← Fama-French (1992)
        F6 fcf_yield              0.15  ← cash-quality value

    Sum is normalised to 1.0 before scoring; UI can pass raw drag values.
    """

    model_config = ConfigDict(extra="forbid")

    f1_roe: float = Field(default=0.15, ge=0)
    f2_gross_profit_to_assets: float = Field(default=0.20, ge=0)
    f3_debt_to_equity: float = Field(default=0.15, ge=0)
    f4_earnings_yield: float = Field(default=0.20, ge=0)
    f5_book_to_market: float = Field(default=0.15, ge=0)
    f6_fcf_yield: float = Field(default=0.15, ge=0)

    def normalised(self) -> "QvWeights":
        total = (
            self.f1_roe + self.f2_gross_profit_to_assets + self.f3_debt_to_equity
            + self.f4_earnings_yield + self.f5_book_to_market + self.f6_fcf_yield
        )
        if total <= 0:
            return QvWeights()
        return QvWeights(
            f1_roe=self.f1_roe / total,
            f2_gross_profit_to_assets=self.f2_gross_profit_to_assets / total,
            f3_debt_to_equity=self.f3_debt_to_equity / total,
            f4_earnings_yield=self.f4_earnings_yield / total,
            f5_book_to_market=self.f5_book_to_market / total,
            f6_fcf_yield=self.f6_fcf_yield / total,
        )


class BosFlowWeights(BaseModel):
    """Per-factor weights for the BOS-Flow engine (7 factors).

    Adds insider_flow + retail_flow on top of canonical BOS. Defaults bias
    toward the established BOS factors but give flow signals real weight:
        F1=0.15 F2=0.15 F3=0.15 F4=0.20 F5=0.10 F6=0.15 F7=0.10  (sum=1.00)
    Sum is normalised to 1.0 before scoring; the UI can pass raw drag values.
    """

    model_config = ConfigDict(extra="forbid")

    f1_volume: float = Field(default=0.15, ge=0)
    f2_target: float = Field(default=0.15, ge=0)
    f3_dvd_yld: float = Field(default=0.15, ge=0)
    f4_altman_z: float = Field(default=0.20, ge=0)
    f5_analyst_sent: float = Field(default=0.10, ge=0)
    f6_insider_flow: float = Field(default=0.15, ge=0)
    f7_retail_flow: float = Field(default=0.10, ge=0)

    def normalised(self) -> "BosFlowWeights":
        total = (
            self.f1_volume + self.f2_target + self.f3_dvd_yld
            + self.f4_altman_z + self.f5_analyst_sent
            + self.f6_insider_flow + self.f7_retail_flow
        )
        if total <= 0:
            return BosFlowWeights()
        return BosFlowWeights(
            f1_volume=self.f1_volume / total,
            f2_target=self.f2_target / total,
            f3_dvd_yld=self.f3_dvd_yld / total,
            f4_altman_z=self.f4_altman_z / total,
            f5_analyst_sent=self.f5_analyst_sent / total,
            f6_insider_flow=self.f6_insider_flow / total,
            f7_retail_flow=self.f7_retail_flow / total,
        )


class ScoreRequest(BaseModel):
    """Generic request — universe-agnostic. Each row is a dict of canonical fields."""

    model_config = ConfigDict(extra="forbid")

    universe: str = Field(default="CSV", description="KLCI | SP500 | CSV | <custom>")
    rows: list[dict[str, Any]]
    options: dict[str, Any] = Field(default_factory=dict)
    bos_weights: BosWeights | None = Field(
        default=None,
        description="Optional override for BOS factor weights. Ignored by MOS/4F/bos_flow.",
    )
    bos_flow_weights: BosFlowWeights | None = Field(
        default=None,
        description="Optional override for BOS-Flow factor weights. Ignored by other models.",
    )
    qv_weights: QvWeights | None = Field(
        default=None,
        description="Optional override for QV (Quality-Value) factor weights. Ignored by other models.",
    )


class ScoreResponse(BaseModel):
    model_version: str
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    universe: str
    n_rows: int
    n_scored: int
    results: list[StockResult]
    warnings: list[str] = Field(default_factory=list)
