"""MLA — Machine-Learning Algorithm scoring engine (P5).

Shares ScoreResponse with RBA. Same input rows, same output schema; the only
difference is the function that turns factor inputs into final_score. RBA
applies a hand-tuned weighted sum; MLA uses a trained gradient-boosted
regressor that can capture non-linear interactions RBA cannot.

Promotion gate (`gate.evaluate_promotion`) MUST pass before MLA is exposed in
production. The gate compares MLA vs RBA backtest metrics on the same period.
"""
from .gate import PromotionDecision, evaluate_promotion
from .inference import score_mla_v0
from .model import MlaScorer

__all__ = [
    "MlaScorer",
    "PromotionDecision",
    "evaluate_promotion",
    "score_mla_v0",
]
