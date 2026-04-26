"""score_mla_v0 — inference path matching the RBA contract.

Same input shape as score_bos. Returns a ScoreResponse with model_version
"mla-v0.1.0". Quartiles assigned identically to BOS so the UI's recommendation
chip just works.

The model artifact is loaded lazily from a path that defaults to
``packages/algorithms/trio_algorithms/mla/artifacts/mla_v0.joblib``. If the
artifact is missing, a fresh model is trained on the spot from a fixed seed —
useful for tests + first-run UX, surfaced as a warning in the response.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .._common import assign_quartiles
from ..contracts import (
    QUARTILE_TO_RECOMMENDATION,
    FactorBreakdown,
    Recommendation,
    ScoreResponse,
    StockResult,
)
from .model import FEATURE_ORDER, MlaScorer

MODEL_VERSION = "mla-v0.1.0"
DEFAULT_ARTIFACT = (
    Path(__file__).parent / "artifacts" / "mla_v0.joblib"
)

_FACTOR_LABELS = {
    "vol_avg_3m": "Volume Avg 3M",
    "target_return": "Target Return %",
    "dvd_yld_ind": "Dividend Yield %",
    "altman_z": "Altman Z-Score",
    "analyst_sent": "Analyst Sentiment",
    "insider_flow": "Insider Flow",
    "retail_flow": "Retail Flow",
}

# Factors that may be missing from a PIT input row. Score_mla_v0 substitutes
# the same placeholder the training pipeline uses so inference matches train.
# - target_return / analyst_sent: forward-looking analyst data, often None
#   when FmpPitProvider is not enabled.
# - insider_flow / retail_flow: missing when no CIK/Wikipedia mapping exists.
_PIT_PLACEHOLDERS: dict[str, float] = {
    "target_return": 0.0,
    "analyst_sent": 3.0,
    "insider_flow": 3.0,   # neutral
    "retail_flow": 3.0,    # neutral
}

_cached: MlaScorer | None = None
_cache_path: Path | None = None


def _load_or_train(artifact: Path) -> tuple[MlaScorer, list[str]]:
    global _cached, _cache_path
    if _cached is not None and _cache_path == artifact:
        return _cached, []

    warnings: list[str] = []
    if artifact.exists():
        scorer = MlaScorer.load(artifact)
    else:
        # First-run / test-time fallback. Imported lazily so prod deploys
        # without a baked artifact still work.
        from .train import train
        scorer = train()
        warnings.append(
            f"mla-v0 artifact missing at {artifact} — trained an in-memory "
            f"model from synthetic data (r2={scorer.meta.train_r2:.3f})."
        )
    _cached = scorer
    _cache_path = artifact
    return scorer, warnings


def score_mla_v0(
    rows: list[dict[str, Any]],
    *,
    universe: str = "CSV",
    artifact: Path | None = None,
) -> ScoreResponse:
    scorer, warnings = _load_or_train(artifact or DEFAULT_ARTIFACT)
    if scorer.meta:
        warnings.append(
            f"mla-v0 trained on {scorer.meta.n_samples} synthetic samples "
            f"(r2={scorer.meta.train_r2:.3f}, RBA-corr={scorer.meta.rba_corr:.3f}). "
            "Replace with PIT-trained artifact before promoting."
        )

    results: list[StockResult] = []
    raw_scores: list[float | None] = []
    for row in rows:
        # Fill in placeholders for forward-looking factors when missing
        # (PIT path); pass through untouched otherwise.
        scoring_row = dict(row)
        used_placeholders: list[str] = []
        for k, default in _PIT_PLACEHOLDERS.items():
            if scoring_row.get(k) is None:
                scoring_row[k] = default
                used_placeholders.append(k)
        score = scorer.score_row(scoring_row)
        raw_scores.append(score)
        # Per-factor breakdown — band/contribution computed against feature
        # importance for transparency. We don't claim per-factor weights are
        # the same as RBA; we surface importance instead.
        breakdowns: list[FactorBreakdown] = []
        importances = (
            scorer.model.feature_importances_  # type: ignore[union-attr]
            if scorer.model is not None else [0.0] * len(FEATURE_ORDER)
        )
        for fid, imp in zip(FEATURE_ORDER, importances):
            raw = row.get(fid)
            try:
                raw_f: float | None = float(raw) if raw is not None else None
            except (TypeError, ValueError):
                raw_f = None
            breakdowns.append(FactorBreakdown(
                id=fid.upper(),
                label=_FACTOR_LABELS.get(fid, fid),
                raw=raw_f,
                band="N/A",
                sub_score=0.0,
                weight=float(imp),
                contribution=0.0,
                flags=["mla_importance"] if raw_f is not None else ["missing"],
            ))
        results.append(StockResult(
            ticker=str(row.get("ticker") or "?"),
            name=row.get("name"),
            final_score=score,
            quartile=None,
            recommendation=Recommendation.UNRANKED,
            factors=breakdowns,
            explanation=(
                f"MLA score {score:.2f} (gradient-boosted over 5 factors)."
                if score is not None else "Insufficient data — no factors available."
            ),
        ))

    quartiles = assign_quartiles(raw_scores, ascending=False)
    for r, q in zip(results, quartiles):
        r.quartile = q
        if q is not None:
            r.recommendation = QUARTILE_TO_RECOMMENDATION[q]

    n_scored = sum(1 for s in raw_scores if s is not None)
    if n_scored < 4:
        warnings.append(f"Universe has only {n_scored} scorable rows; quartiles not assigned.")

    return ScoreResponse(
        model_version=MODEL_VERSION,
        universe=universe,
        n_rows=len(rows),
        n_scored=n_scored,
        results=results,
        warnings=warnings,
    )
