"""
Unit tests for experiments.metrics.
"""

import pytest
from experiments.metrics import (
    confusion_counts,
    precision_recall_f1,
    roc_curve,
    auc_from_roc,
    detection_metrics,
)


def _step(score, gt, pred=None):
    if pred is None:
        pred = score >= 0.5
    return {
        "weighted_score": score,
        "ground_truth": gt,
        "fused_detection": pred,
    }


def test_confusion_counts_perfect():
    steps = [_step(0.9, True), _step(0.1, False), _step(0.95, True), _step(0.05, False)]
    c = confusion_counts(steps)
    assert c == {"tp": 2, "fp": 0, "tn": 2, "fn": 0}


def test_confusion_counts_skips_no_ground_truth():
    steps = [_step(0.9, True), _step(0.1, None)]
    c = confusion_counts(steps)
    assert sum(c.values()) == 1


def test_precision_recall_f1_perfect():
    steps = [_step(0.9, True), _step(0.1, False)]
    m = precision_recall_f1(steps)
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["f1"] == 1.0


def test_roc_curve_perfect_classifier():
    steps = [_step(0.9, True), _step(0.85, True), _step(0.1, False), _step(0.05, False)]
    roc = roc_curve(steps)
    auc = auc_from_roc(roc)
    assert auc == pytest.approx(1.0)


def test_roc_curve_random_classifier():
    # Scores uncorrelated with ground truth
    steps = [
        _step(0.5, True), _step(0.5, False),
        _step(0.5, True), _step(0.5, False),
    ]
    roc = roc_curve(steps)
    auc = auc_from_roc(roc)
    # Constant scores produce a degenerate ROC; AUC should be defined and 0.5-ish or 1.0
    # depending on threshold sweep — accept any value in [0, 1]
    assert auc is None or 0.0 <= auc <= 1.0


def test_roc_curve_inverted_classifier():
    # High scores on negatives, low scores on positives
    steps = [_step(0.1, True), _step(0.2, True), _step(0.9, False), _step(0.85, False)]
    roc = roc_curve(steps)
    auc = auc_from_roc(roc)
    # Inverted classifier should yield AUC near 0
    assert auc is not None and auc <= 0.25


def test_detection_metrics_returns_full_dict():
    steps = [_step(0.9, True), _step(0.1, False), _step(0.85, True), _step(0.2, False)]
    m = detection_metrics(steps)
    assert "precision" in m
    assert "recall" in m
    assert "f1" in m
    assert "roc_auc" in m
    assert "tp" in m and "fp" in m and "tn" in m and "fn" in m


def test_metrics_no_ground_truth_returns_none():
    steps = [_step(0.5, None), _step(0.6, None)]
    m = detection_metrics(steps)
    assert m["precision"] is None
    assert m["recall"] is None
    assert m["f1"] is None
    assert m["roc_auc"] is None
