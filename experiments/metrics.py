"""
Detection-quality metrics for binary classification with ground truth.

Adds ROC, AUC, precision, recall, and F1 to the experiment summary.
Uses pure-Python implementations so no scikit-learn dependency is required.

Why this matters
----------------
The original runner reports only accuracy and "false HIGH confidence count."
That's not enough to compare fusion methods rigorously: a method can have
high accuracy at one threshold but terrible behavior at others. ROC/AUC
captures performance across all thresholds and is the standard metric
expected by anyone reviewing a detection system.
"""

from __future__ import annotations


def confusion_counts(steps: list[dict]) -> dict[str, int]:
    """Compute TP/FP/TN/FN over steps that have ground truth."""
    tp = fp = tn = fn = 0
    for s in steps:
        gt = s.get("ground_truth")
        pred = s.get("fused_detection")
        if gt is None:
            continue
        if pred and gt:
            tp += 1
        elif pred and not gt:
            fp += 1
        elif not pred and not gt:
            tn += 1
        else:
            fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def precision_recall_f1(steps: list[dict]) -> dict[str, float | None]:
    cc = confusion_counts(steps)
    tp, fp, fn = cc["tp"], cc["fp"], cc["fn"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = None
    return {
        "precision": round(precision, 3) if precision is not None else None,
        "recall": round(recall, 3) if recall is not None else None,
        "f1": round(f1, 3) if f1 is not None else None,
        **cc,
    }


def roc_curve(steps: list[dict]) -> dict[str, list[float]]:
    """
    Sweep detection thresholds across all observed weighted_scores and
    compute (FPR, TPR) points. Returns sorted thresholds and the curves.

    Only includes steps with ground truth. Scores can come from any
    fusion method as long as they live in steps[i]["weighted_score"].

    When the ground truth contains only positives or only negatives, the
    ROC curve is degenerate and AUC is undefined; in that case the curves
    are returned empty so auc_from_roc() can return None.
    """
    pts = [
        (float(s["weighted_score"]), bool(s["ground_truth"]))
        for s in steps
        if s.get("ground_truth") is not None
    ]
    if not pts:
        return {"thresholds": [], "fpr": [], "tpr": [], "degenerate": True}

    P = sum(1 for _, gt in pts if gt)
    N = sum(1 for _, gt in pts if not gt)

    # Both classes are required for a meaningful ROC curve.
    if P == 0 or N == 0:
        return {"thresholds": [], "fpr": [], "tpr": [], "degenerate": True}

    thresholds = sorted({score for score, _ in pts} | {0.0, 1.0}, reverse=True)
    fpr_list, tpr_list = [], []
    for thr in thresholds:
        tp = sum(1 for score, gt in pts if gt and score >= thr)
        fp = sum(1 for score, gt in pts if not gt and score >= thr)
        tpr = tp / P if P > 0 else 0.0
        fpr = fp / N if N > 0 else 0.0
        tpr_list.append(round(tpr, 4))
        fpr_list.append(round(fpr, 4))

    return {"thresholds": thresholds, "fpr": fpr_list, "tpr": tpr_list}


def auc_from_roc(roc: dict) -> float | None:
    """
    Trapezoidal AUC from a ROC curve dict. Returns None when the curve
    is degenerate (no positives or no negatives).
    """
    if roc.get("degenerate"):
        return None
    fpr = roc.get("fpr", [])
    tpr = roc.get("tpr", [])
    if len(fpr) < 2 or len(tpr) < 2:
        return None

    # Sort by fpr ascending for stable trapezoidal integration
    order = sorted(range(len(fpr)), key=lambda i: (fpr[i], tpr[i]))
    fpr_s = [fpr[i] for i in order]
    tpr_s = [tpr[i] for i in order]

    auc = 0.0
    for i in range(1, len(fpr_s)):
        dx = fpr_s[i] - fpr_s[i - 1]
        avg_y = (tpr_s[i] + tpr_s[i - 1]) / 2.0
        auc += dx * avg_y
    return round(auc, 4)


def detection_metrics(steps: list[dict]) -> dict:
    """
    Compute the full set of detection-quality metrics for a result's steps.
    Returns a dict suitable for inclusion in the experiment summary.
    """
    prf = precision_recall_f1(steps)
    roc = roc_curve(steps)
    auc = auc_from_roc(roc)
    return {
        **prf,
        "roc_auc": auc,
        # Don't include the full ROC curve in the summary by default —
        # callers can request it via roc_curve() directly. Including it
        # would inflate every results JSON unnecessarily.
    }
