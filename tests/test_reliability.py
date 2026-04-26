"""
Unit tests for data_fusion.reliability_memory.
"""

import pytest
from data_fusion.reliability_memory import update_reliability_history, get_reliability_factor


def _sensor(name, quality, latency):
    return {"sensor": name, "detected": True, "quality": quality, "latency": latency}


# ── get_reliability_factor ────────────────────────────────────────────────────

def test_unknown_sensor_returns_default_1():
    """A sensor with no history should get full trust (benefit of the doubt)."""
    assert get_reliability_factor({}, "UNKNOWN") == 1.0


def test_high_reliability_history_returns_1():
    history = {"A": [0.9, 0.9, 0.9, 0.85]}
    assert get_reliability_factor(history, "A") == 1.0


def test_good_reliability_returns_0_9():
    history = {"A": [0.7, 0.65, 0.70, 0.68]}
    factor = get_reliability_factor(history, "A")
    assert factor == 0.9


def test_moderate_reliability_returns_0_75():
    history = {"A": [0.5, 0.45, 0.50, 0.48]}
    factor = get_reliability_factor(history, "A")
    assert factor == 0.75


def test_poor_reliability_returns_0_6():
    history = {"A": [0.2, 0.25, 0.20, 0.18]}
    factor = get_reliability_factor(history, "A")
    assert factor == 0.6


def test_reliability_factor_never_below_0_6():
    """Even a completely failed sensor should have a floor of 0.6."""
    history = {"A": [0.0, 0.0, 0.0, 0.0]}
    factor = get_reliability_factor(history, "A")
    assert factor >= 0.6


def test_reliability_factor_never_above_1():
    history = {"A": [1.0, 1.0, 1.0]}
    factor = get_reliability_factor(history, "A")
    assert factor <= 1.0


# ── update_reliability_history ────────────────────────────────────────────────

def test_history_accumulates_with_each_update():
    history = {}
    step1 = [_sensor("A", 0.90, 100)]
    history = update_reliability_history(history, step1)
    assert "A" in history
    assert len(history["A"]) == 1

    step2 = [_sensor("A", 0.85, 120)]
    history = update_reliability_history(history, step2)
    assert len(history["A"]) == 2


def test_multiple_sensors_tracked_independently():
    history = {}
    step = [_sensor("A", 0.90, 100), _sensor("B", 0.70, 200)]
    history = update_reliability_history(history, step)
    assert "A" in history
    assert "B" in history
    assert len(history["A"]) == 1
    assert len(history["B"]) == 1


def test_reliability_sample_reflects_quality_and_latency():
    """
    High quality + low latency → high sample.
    Low quality + high latency → low sample.
    """
    h1 = update_reliability_history({}, [_sensor("A", 0.90, 100)])
    h2 = update_reliability_history({}, [_sensor("B", 0.20, 900)])
    assert h1["A"][0] > h2["B"][0]


def test_new_sensor_in_step_initialises_correctly():
    history = {"A": [0.8, 0.8]}
    step = [_sensor("A", 0.85, 110), _sensor("NEW", 0.75, 150)]
    history = update_reliability_history(history, step)
    assert "NEW" in history
    assert len(history["NEW"]) == 1
    assert len(history["A"]) == 3


def test_update_does_not_mutate_sensor_data():
    """update_reliability_history should not modify the sensor_data list in place."""
    import copy
    step = [_sensor("A", 0.90, 100)]
    original = copy.deepcopy(step)
    update_reliability_history({}, step)
    assert step == original
