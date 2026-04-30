"""
Unit tests for data_fusion.disagreement (entropy-based penalty).
"""

import pytest

from data_fusion.disagreement import (
    binary_entropy,
    weighted_disagreement_penalty,
    legacy_flat_penalty,
)


def test_entropy_at_zero_or_one_is_zero():
    assert binary_entropy(0.0) == 0.0
    assert binary_entropy(1.0) == 0.0


def test_entropy_at_half_is_one_bit():
    assert binary_entropy(0.5) == pytest.approx(1.0)


def test_entropy_symmetric():
    assert binary_entropy(0.3) == pytest.approx(binary_entropy(0.7))


# ── weighted_disagreement_penalty ────────────────────────────────────────────

def test_unanimous_agreement_no_penalty():
    # All weight on positive
    assert weighted_disagreement_penalty(positive_weight=2.0, total_weight=2.0) == 1.0
    # All weight on negative
    assert weighted_disagreement_penalty(positive_weight=0.0, total_weight=2.0) == 1.0


def test_max_disagreement_applies_alpha():
    # 50/50 split => entropy = 1, penalty = 1 - alpha
    assert weighted_disagreement_penalty(1.0, 2.0, alpha=0.4) == pytest.approx(0.6)
    assert weighted_disagreement_penalty(1.0, 2.0, alpha=1.0) == pytest.approx(0.0)
    assert weighted_disagreement_penalty(1.0, 2.0, alpha=0.0) == pytest.approx(1.0)


def test_partial_disagreement_in_range():
    # 80/20 weight split should give a moderate penalty between max and 1
    p = weighted_disagreement_penalty(0.8, 1.0, alpha=0.4)
    assert 0.6 < p < 1.0


def test_zero_total_weight_returns_one():
    assert weighted_disagreement_penalty(0.0, 0.0) == 1.0


def test_invalid_alpha_raises():
    with pytest.raises(ValueError):
        weighted_disagreement_penalty(1.0, 2.0, alpha=1.5)
    with pytest.raises(ValueError):
        weighted_disagreement_penalty(1.0, 2.0, alpha=-0.1)


# ── Legacy fallback ──────────────────────────────────────────────────────────

def test_legacy_flat_penalty():
    assert legacy_flat_penalty(False) == 1.0
    assert legacy_flat_penalty(True) == 0.8
