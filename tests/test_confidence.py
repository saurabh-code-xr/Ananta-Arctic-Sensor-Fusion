"""
Unit tests for data_fusion.confidence_engine.
"""

import pytest
from data_fusion.confidence_engine import compute_confidence


def _fusion(score, quality, latency, disagreement=False):
    return {
        "weighted_detection_score": score,
        "avg_quality": quality,
        "avg_latency": latency,
        "disagreement": disagreement,
    }


def _sensors(*tuples):
    """Helper: list of (name, quality, latency) → sensor dicts."""
    return [{"sensor": n, "quality": q, "latency": l, "detected": True} for n, q, l in tuples]


# ── Confidence level classification ──────────────────────────────────────────

def test_high_confidence_conditions():
    fusion = _fusion(score=0.90, quality=0.88, latency=150)
    sensors = _sensors(("A", 0.88, 150), ("B", 0.90, 140))
    result = compute_confidence(fusion, sensors)
    assert result["level"] == "HIGH"


def test_low_score_produces_low_confidence():
    fusion = _fusion(score=0.30, quality=0.40, latency=600)
    sensors = _sensors(("A", 0.40, 600))
    result = compute_confidence(fusion, sensors)
    assert result["level"] == "LOW"


def test_disagreement_prevents_high_confidence():
    """Even a good weighted score should not produce HIGH if sensors disagree."""
    fusion = _fusion(score=0.85, quality=0.88, latency=150, disagreement=True)
    sensors = _sensors(("A", 0.88, 150), ("B", 0.88, 150))
    result = compute_confidence(fusion, sensors)
    assert result["level"] != "HIGH"


def test_high_latency_degrades_confidence():
    """High avg_latency should prevent HIGH confidence."""
    fusion = _fusion(score=0.90, quality=0.88, latency=700)
    sensors = _sensors(("A", 0.88, 700))
    result = compute_confidence(fusion, sensors)
    assert result["level"] != "HIGH"


def test_medium_band_classification():
    fusion = _fusion(score=0.65, quality=0.60, latency=300)
    sensors = _sensors(("A", 0.60, 300))
    result = compute_confidence(fusion, sensors)
    assert result["level"] == "MEDIUM"


# ── Reasons and actions ───────────────────────────────────────────────────────

def test_always_has_recommended_actions():
    for score, quality, latency in [(0.9, 0.9, 100), (0.6, 0.6, 300), (0.2, 0.3, 700)]:
        fusion = _fusion(score=score, quality=quality, latency=latency)
        sensors = _sensors(("A", quality, latency))
        result = compute_confidence(fusion, sensors)
        assert len(result["actions"]) > 0, f"No actions for score={score}"


def test_disagreement_in_reasons_when_flagged():
    fusion = _fusion(score=0.85, quality=0.88, latency=150, disagreement=True)
    sensors = _sensors(("A", 0.88, 150))
    result = compute_confidence(fusion, sensors)
    assert any("disagreement" in r for r in result["reasons"])


def test_low_quality_sensor_named_in_reasons():
    fusion = _fusion(score=0.60, quality=0.40, latency=200)
    sensors = _sensors(("A", 0.40, 200), ("B", 0.90, 100))
    fusion["avg_quality"] = 0.65  # override avg
    result = compute_confidence(fusion, sensors)
    assert any("A" in r for r in result["reasons"])


def test_high_latency_sensor_named_in_reasons():
    fusion = _fusion(score=0.70, quality=0.80, latency=500)
    sensors = _sensors(("A", 0.80, 600))
    result = compute_confidence(fusion, sensors)
    assert any("A" in r for r in result["reasons"])


# ── Output schema ─────────────────────────────────────────────────────────────

def test_output_contains_required_keys():
    fusion = _fusion(score=0.80, quality=0.80, latency=150)
    sensors = _sensors(("A", 0.80, 150))
    result = compute_confidence(fusion, sensors)
    assert {"level", "weighted_score", "reasons", "actions"}.issubset(result.keys())


def test_level_is_valid_string():
    fusion = _fusion(score=0.80, quality=0.80, latency=150)
    sensors = _sensors(("A", 0.80, 150))
    result = compute_confidence(fusion, sensors)
    assert result["level"] in ("HIGH", "MEDIUM", "LOW")


# ── Custom thresholds ─────────────────────────────────────────────────────────

def test_custom_thresholds_override_defaults():
    """Lowering the HIGH threshold should make a medium score classify as HIGH."""
    fusion = _fusion(score=0.65, quality=0.65, latency=180)
    sensors = _sensors(("A", 0.65, 180))
    default_result = compute_confidence(fusion, sensors)
    strict_thresholds = {"high_score": 0.60, "high_quality": 0.60, "high_latency_ceiling": 200}
    lenient_result = compute_confidence(fusion, sensors, thresholds=strict_thresholds)
    # default should be MEDIUM or LOW; lenient should be HIGH
    assert default_result["level"] in ("MEDIUM", "LOW")
    assert lenient_result["level"] == "HIGH"
