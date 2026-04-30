"""
Unit tests for data_fusion.freshness (continuous decay functions).
"""

import math
import pytest

from data_fusion.freshness import (
    exponential_decay,
    linear_decay,
    sigmoid_decay,
    freshness_continuous,
)


# ── Exponential decay ────────────────────────────────────────────────────────

def test_exponential_at_zero_is_one():
    assert exponential_decay(0.0) == pytest.approx(1.0)


def test_exponential_decreases_monotonically():
    a = exponential_decay(50.0)
    b = exponential_decay(100.0)
    c = exponential_decay(500.0)
    assert a > b > c


def test_exponential_respects_floor():
    # very large latency should still hit the floor, not go below
    assert exponential_decay(10_000.0, floor=0.05) >= 0.05


def test_exponential_negative_latency_clamps_to_zero():
    assert exponential_decay(-50.0) == pytest.approx(1.0)


def test_exponential_invalid_tau_raises():
    with pytest.raises(ValueError):
        exponential_decay(100.0, tau_ms=0.0)


def test_exponential_at_tau_is_one_over_e():
    # f(tau) = exp(-1) ≈ 0.3679
    assert exponential_decay(250.0, tau_ms=250.0) == pytest.approx(math.exp(-1), rel=1e-3)


# ── Linear decay ─────────────────────────────────────────────────────────────

def test_linear_zero_is_one():
    assert linear_decay(0.0) == pytest.approx(1.0)


def test_linear_at_t_max_hits_floor():
    assert linear_decay(800.0, t_max_ms=800.0, floor=0.05) == pytest.approx(0.05)


def test_linear_beyond_t_max_clamped_to_floor():
    assert linear_decay(2000.0, t_max_ms=800.0, floor=0.05) == 0.05


def test_linear_invalid_t_max_raises():
    with pytest.raises(ValueError):
        linear_decay(100.0, t_max_ms=-1.0)


# ── Sigmoid decay ────────────────────────────────────────────────────────────

def test_sigmoid_at_t0_is_half():
    assert sigmoid_decay(300.0, t0_ms=300.0, k_ms=80.0) == pytest.approx(0.5, rel=1e-3)


def test_sigmoid_below_knee_is_high():
    assert sigmoid_decay(50.0, t0_ms=300.0) > 0.9


def test_sigmoid_above_knee_is_low():
    assert sigmoid_decay(800.0, t0_ms=300.0, k_ms=80.0) < 0.1


def test_sigmoid_invalid_k_raises():
    with pytest.raises(ValueError):
        sigmoid_decay(100.0, k_ms=0.0)


# ── Config-driven dispatcher ─────────────────────────────────────────────────

def test_freshness_continuous_no_config_uses_exponential():
    # Default tau_ms is 500 (marine/satellite safe).
    # At latency = tau_ms, decay = exp(-1) ≈ 0.368.
    assert freshness_continuous(0.0) == pytest.approx(1.0)
    assert freshness_continuous(500.0) == pytest.approx(math.exp(-1), rel=1e-3)


def test_freshness_continuous_unknown_model_falls_back_to_exponential():
    cfg = {"fusion": {"freshness_continuous": {"model": "lol_not_a_model"}}}
    assert freshness_continuous(0.0, config=cfg) == pytest.approx(1.0)


def test_freshness_continuous_uses_configured_model():
    cfg = {"fusion": {"freshness_continuous": {"model": "linear", "t_max_ms": 1000.0}}}
    assert freshness_continuous(500.0, config=cfg) == pytest.approx(0.5, rel=1e-3)


def test_freshness_continuous_bad_params_falls_back_to_defaults():
    # tau_ms=0 would normally raise; the dispatcher should swallow and fall back.
    cfg = {"fusion": {"freshness_continuous": {"model": "exponential", "tau_ms": 0.0}}}
    # Should use exponential_decay with default tau_ms=250 (no exception)
    assert 0.0 < freshness_continuous(100.0, config=cfg) <= 1.0
