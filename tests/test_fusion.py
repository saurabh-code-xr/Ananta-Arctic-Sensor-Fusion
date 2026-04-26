"""
Unit tests for data_fusion.fusion_engine.
"""

import pytest
from data_fusion.fusion_engine import fuse_sensors


def _sensor(name, detected, quality, latency):
    return {"sensor": name, "detected": detected, "quality": quality, "latency": latency}


# ── Input edge cases ──────────────────────────────────────────────────────────

def test_empty_input_returns_safe_defaults():
    result = fuse_sensors([])
    assert result["fused_detection"] is False
    assert result["weighted_detection_score"] == 0.0
    assert result["detected_count"] == 0
    assert result["disagreement"] is False


def test_single_sensor_high_quality():
    data = [_sensor("A", True, 0.95, 100)]
    result = fuse_sensors(data)
    assert result["fused_detection"] is True
    assert result["weighted_detection_score"] > 0.6


def test_single_sensor_not_detected():
    data = [_sensor("A", False, 0.95, 100)]
    result = fuse_sensors(data)
    assert result["fused_detection"] is False
    assert result["weighted_detection_score"] == 0.0


# ── Weighting behaviour ───────────────────────────────────────────────────────

def test_all_agree_high_quality_produces_high_score():
    data = [
        _sensor("A", True, 0.92, 100),
        _sensor("B", True, 0.90, 110),
        _sensor("C", True, 0.91, 105),
    ]
    result = fuse_sensors(data)
    assert result["fused_detection"] is True
    assert result["weighted_detection_score"] >= 0.8


def test_disagreement_flag_set_when_sensors_conflict():
    data = [
        _sensor("A", True, 0.90, 100),
        _sensor("B", False, 0.90, 100),
    ]
    result = fuse_sensors(data)
    assert result["disagreement"] is True


def test_disagreement_penalty_reduces_score():
    data_agree = [
        _sensor("A", True, 0.90, 100),
        _sensor("B", True, 0.90, 100),
    ]
    data_conflict = [
        _sensor("A", True, 0.90, 100),
        _sensor("B", False, 0.90, 100),
    ]
    agree_score = fuse_sensors(data_agree)["weighted_detection_score"]
    conflict_score = fuse_sensors(data_conflict)["weighted_detection_score"]
    assert conflict_score < agree_score


def test_high_latency_reduces_weight():
    """
    With two sensors in conflict, a higher-quality/fresh sensor detecting True
    should produce a higher score than when the detecting sensor is stale.

    Weighting normalises to 1.0 with a single sensor, so this must use two sensors.
    """
    # A (True, fresh) vs B (False, fresh) — A should win comfortably
    data_fresh = [_sensor("A", True, 0.90, 100), _sensor("B", False, 0.90, 100)]
    # A (True, stale) vs B (False, fresh) — A's contribution is reduced
    data_stale = [_sensor("A", True, 0.90, 800), _sensor("B", False, 0.90, 100)]
    fresh_score = fuse_sensors(data_fresh)["weighted_detection_score"]
    stale_score = fuse_sensors(data_stale)["weighted_detection_score"]
    assert stale_score < fresh_score


def test_low_quality_reduces_score():
    """
    With two sensors in conflict, the detecting sensor having lower quality
    should produce a lower fused detection score.
    """
    # A (True, high quality) vs B (False, high quality) — roughly balanced, slight positive
    data_good = [_sensor("A", True, 0.90, 100), _sensor("B", False, 0.30, 100)]
    # A (True, low quality) vs B (False, high quality) — B dominates
    data_poor = [_sensor("A", True, 0.20, 100), _sensor("B", False, 0.90, 100)]
    good_score = fuse_sensors(data_good)["weighted_detection_score"]
    poor_score = fuse_sensors(data_poor)["weighted_detection_score"]
    assert poor_score < good_score


# ── Reliability memory ────────────────────────────────────────────────────────

def test_poor_reliability_history_reduces_contribution():
    """
    With two conflicting sensors, the one with poor reliability history
    should have less influence — resulting in a lower detection score when
    the poor-reliability sensor is the one detecting True.
    """
    poor_history = {"A": [0.2, 0.2, 0.2, 0.2, 0.2]}
    good_history = {"A": [0.9, 0.9, 0.9, 0.9, 0.9]}

    # A (True) vs B (False) — A's reliability_factor changes
    data = [_sensor("A", True, 0.90, 100), _sensor("B", False, 0.90, 100)]
    poor_result = fuse_sensors(data, reliability_history=poor_history)
    good_result = fuse_sensors(data, reliability_history=good_history)

    assert poor_result["weighted_detection_score"] < good_result["weighted_detection_score"]


def test_no_reliability_history_uses_default():
    """Unknown sensor should default to reliability_factor=1.0 (benefit of the doubt)."""
    data = [_sensor("NEW", True, 0.90, 100)]
    result = fuse_sensors(data, reliability_history={})
    assert result["per_sensor_weights"]["NEW"]["reliability_factor"] == 1.0


# ── Output schema ─────────────────────────────────────────────────────────────

def test_output_contains_required_keys():
    data = [_sensor("A", True, 0.90, 100)]
    result = fuse_sensors(data)
    required = {
        "detected_count", "avg_quality", "avg_latency",
        "raw_weighted_detection_score", "weighted_detection_score",
        "fused_detection", "per_sensor_weights", "disagreement", "disagreement_penalty",
    }
    assert required.issubset(result.keys())


def test_fused_detection_is_bool():
    data = [_sensor("A", True, 0.90, 100)]
    result = fuse_sensors(data)
    assert isinstance(result["fused_detection"], bool)
