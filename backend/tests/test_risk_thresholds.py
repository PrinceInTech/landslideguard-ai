"""Risk threshold centralization.

The boundaries previously existed in four places and could disagree. These tests
pin the canonical behaviour and assert that every consumer agrees.
"""
import json
from pathlib import Path

import pytest

from app.risk import RISK_BOUNDARIES, RISK_LEVELS, classify_risk, clamp_score
from app.services.analytics_service import state_risk_summary

BACKEND_DIR = Path(__file__).resolve().parent.parent
MODEL_META = BACKEND_DIR.parent / "ml" / "model" / "model_meta.json"


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "LOW"),
        (0.1, "LOW"),
        (29.999, "LOW"),
        (30, "LOW"),  # upper bound is inclusive
        (30.001, "MODERATE"),
        (60, "MODERATE"),
        (60.001, "HIGH"),
        (80, "HIGH"),
        (80.001, "CRITICAL"),
        (100, "CRITICAL"),
    ],
)
def test_classify_risk_boundaries(score, expected):
    assert classify_risk(score) == expected


def test_classify_risk_clamps_out_of_range():
    assert classify_risk(-50) == "LOW"
    assert classify_risk(1000) == "CRITICAL"
    assert clamp_score(-50) == 0.0
    assert clamp_score(1000) == 100.0


def test_levels_are_ordered_and_tile_the_domain():
    assert [level for level, _ in RISK_LEVELS] == ["LOW", "MODERATE", "HIGH", "CRITICAL"]
    assert RISK_LEVELS[0][1] == 30.0
    assert RISK_LEVELS[-1][1] == 100.0
    # Monotonically increasing upper bounds => no gaps, no overlaps.
    bounds = [upper for _, upper in RISK_LEVELS]
    assert bounds == sorted(bounds)
    assert len(set(bounds)) == len(bounds)


def test_analytics_uses_the_same_thresholds(client):
    """Analytics must classify with the canonical function.

    Depends on `client` so the app is rebound to the temporary test database and
    seeded deterministically; without it this would read the developer's real
    landslideguard.db.
    """
    summary = state_risk_summary()
    assert summary, "expected one entry per state"
    # Seeded locations exist, so assert per-row agreement with the canonical
    # classifier rather than assuming an empty database.
    for row in summary:
        assert row["risk_level"] == classify_risk(row["avg_risk_score"]), (
            f"{row['state']}: analytics bucketed {row['avg_risk_score']} as "
            f"{row['risk_level']}, expected {classify_risk(row['avg_risk_score'])}"
        )


def test_predictor_classify_matches_canonical():
    """The predictor must expose the same function, not a private copy."""
    from app.ml.predictor import classify_risk as predictor_classify

    for score in (0, 29.9, 30, 45, 60, 79.9, 80, 99.9, 100):
        assert predictor_classify(score) == classify_risk(score)


def test_model_metadata_thresholds_match_backend():
    """model_meta.json records a snapshot of the boundaries used at train time."""
    meta = json.loads(MODEL_META.read_text(encoding="utf-8"))
    recorded = meta["risk_thresholds"]["upper_bounds"]
    assert recorded == {k: float(v) for k, v in RISK_BOUNDARIES.items()}