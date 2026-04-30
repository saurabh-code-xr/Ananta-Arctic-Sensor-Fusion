"""
Unit tests for data_fusion.kalman_baseline.
"""

import pytest

from data_fusion.kalman_baseline import (
    KalmanBaseline,
    kalman_filter,
    reset_kalman_state,
)


def _sensor(name, detected, quality, latency=100):
    return {"sensor": name, "detected": detected, "quality": quality, "latency": latency}


def test_empty_input_returns_safe_defaults():
    kf = KalmanBaseline()
    out = kf.step([])
    assert out["fused_detection"] in (True, False)
    assert out["weighted_detection_score"] == pytest.approx(0.5, rel=1e-3)


def test_high_quality_detection_drives_score_up():
    kf = KalmanBaseline()
    data = [_sensor("A", True, 0.95, 100),
            _sensor("B", True, 0.95, 100),
            _sensor("C", True, 0.95, 100)]
    out = kf.step(data)
    assert out["weighted_detection_score"] > 0.7
    assert out["fused_detection"] is True


def test_consistent_no_detection_drives_score_down():
    kf = KalmanBaseline()
    for _ in range(3):
        kf.step([_sensor("A", False, 0.9), _sensor("B", False, 0.9), _sensor("C", False, 0.9)])
    # After several "no" updates, score should be low
    assert kf.x < 0.3


def test_state_persists_across_steps():
    kf = KalmanBaseline()
    out1 = kf.step([_sensor("A", True, 0.95)])
    out2 = kf.step([_sensor("A", True, 0.95)])
    # Variance should shrink after more observations
    assert out2["kalman_state_variance"] <= out1["kalman_state_variance"]


def test_low_quality_updates_have_smaller_effect():
    # Two filters: one updated by high-quality reading, one by low-quality.
    kf_hi = KalmanBaseline()
    kf_lo = KalmanBaseline()
    out_hi = kf_hi.step([_sensor("A", True, 0.95, 100)])
    out_lo = kf_lo.step([_sensor("A", True, 0.30, 500)])
    # The high-quality update should pull the state closer to 1.0
    assert out_hi["kalman_state_mean"] > out_lo["kalman_state_mean"]


def test_global_reset_clears_state():
    reset_kalman_state()
    out_first = kalman_filter([_sensor("A", True, 0.95)])
    # Run again without reset — state continues
    out_second = kalman_filter([_sensor("A", True, 0.95)])
    # Now reset and run fresh
    reset_kalman_state()
    out_third = kalman_filter([_sensor("A", True, 0.95)])
    # First and third should be close (fresh state); second should be further along
    assert abs(out_first["kalman_state_mean"] - out_third["kalman_state_mean"]) < 1e-6
    assert out_second["kalman_state_mean"] >= out_first["kalman_state_mean"]
