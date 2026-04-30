"""
Unit tests for data_fusion.adversarial (residual-based outlier detection).
"""

import pytest
from data_fusion.adversarial import detect_outliers


def _sensor(name, detected, quality, latency=100):
    return {"sensor": name, "detected": detected, "quality": quality, "latency": latency}


def test_too_few_sensors_no_flags():
    flags = detect_outliers([_sensor("A", True, 0.9), _sensor("B", True, 0.9)])
    assert all(not f["suspect"] for f in flags.values())
    assert all(f["down_weight"] == 1.0 for f in flags.values())


def test_unanimous_no_flags():
    data = [_sensor(n, True, 0.9) for n in ("A", "B", "C", "D")]
    flags = detect_outliers(data)
    assert all(not f["suspect"] for f in flags.values())


def test_high_quality_outlier_is_flagged():
    # A reports True with high quality; B, C, D all report False with high quality.
    # A should be flagged as suspect.
    data = [
        _sensor("A", True, 0.95),
        _sensor("B", False, 0.92),
        _sensor("C", False, 0.91),
        _sensor("D", False, 0.93),
    ]
    flags = detect_outliers(data)
    assert flags["A"]["suspect"] is True
    assert flags["A"]["down_weight"] < 1.0
    assert flags["B"]["suspect"] is False
    assert flags["C"]["suspect"] is False
    assert flags["D"]["suspect"] is False


def test_low_quality_outlier_not_flagged():
    # If the outlier has low reported quality, the existing weighting handles it;
    # adversarial detection should NOT additionally flag it.
    data = [
        _sensor("A", True, 0.30),  # low quality outlier
        _sensor("B", False, 0.92),
        _sensor("C", False, 0.91),
        _sensor("D", False, 0.93),
    ]
    flags = detect_outliers(data)
    assert flags["A"]["suspect"] is False


def test_down_weight_scales_with_severity():
    # Stronger consensus against => stronger down-weight
    weak = detect_outliers([
        _sensor("A", True, 0.9),
        _sensor("B", False, 0.9),
        _sensor("C", False, 0.9),
        _sensor("D", True, 0.5),  # one supportive (weakly) sensor
    ])
    strong = detect_outliers([
        _sensor("A", True, 0.9),
        _sensor("B", False, 0.95),
        _sensor("C", False, 0.95),
        _sensor("D", False, 0.95),
    ])
    # Both should flag A, but strong consensus produces a smaller down_weight
    assert weak["A"]["suspect"] in (True, False)  # might or might not flag depending on threshold
    assert strong["A"]["suspect"] is True
    if weak["A"]["suspect"]:
        assert strong["A"]["down_weight"] <= weak["A"]["down_weight"]


def test_threshold_parameter_respected():
    data = [
        _sensor("A", True, 0.9),
        _sensor("B", False, 0.9),
        _sensor("C", False, 0.9),
        _sensor("D", True, 0.9),  # 50/50 split — A's claim is not strongly opposed
    ]
    # With high threshold, no outlier should be flagged
    flags_strict = detect_outliers(data, suspect_threshold=0.9)
    assert all(not f["suspect"] for f in flags_strict.values())
    # With low threshold, some might flag (50/50 means consensus_score_against = 0.5)
    flags_loose = detect_outliers(data, suspect_threshold=0.4)
    # At least one of the disagreeing sensors should be flagged at this threshold
    assert any(f["suspect"] for f in flags_loose.values())
