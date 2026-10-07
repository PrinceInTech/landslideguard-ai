"""Canonical risk-level thresholds.

Single source of truth shared by the predictor, API schemas, and analytics
service. Previously these boundaries were duplicated in four places, which
allowed the API and the model output to disagree.

`RISK_LEVELS` is ordered from lowest to highest severity. `upper_bound` is
inclusive and expressed on the same 0-100 scale as `Location.risk_score`.
The half-open integer ranges in `_RISK_BUCKETS` were removed: they disagreed
with the continuous comparisons used at scoring time (a score of 30.5 was
bucketed as MODERATE in one place and LOW in another).
"""
from typing import List, Tuple

RISK_SCORE_MIN = 0.0
RISK_SCORE_MAX = 100.0

RISK_LEVELS: List[Tuple[str, float]] = [
    ("LOW", 30.0),
    ("MODERATE", 60.0),
    ("HIGH", 80.0),
    ("CRITICAL", RISK_SCORE_MAX),
]

RISK_BOUNDARIES = {level: upper for level, upper in RISK_LEVELS}
RISK_LEVEL_NAMES = [level for level, _ in RISK_LEVELS]


def clamp_score(score: float) -> float:
    """Clamp a raw score onto the canonical 0-100 range."""
    return max(RISK_SCORE_MIN, min(RISK_SCORE_MAX, float(score)))


def classify_risk(score: float) -> str:
    """Map a 0-100 risk score onto a risk level.

    Boundaries are inclusive of `upper_bound`, so the ranges tile the whole
    0-100 domain without gaps or overlaps.
    """
    value = clamp_score(score)
    for level, upper_bound in RISK_LEVELS:
        if value <= upper_bound:
            return level
    return RISK_LEVELS[-1][0]
