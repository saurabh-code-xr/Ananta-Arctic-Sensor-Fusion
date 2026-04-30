"""
Principled disagreement penalty.

The original implementation applies a flat 0.8 multiplier whenever
sensors disagree, regardless of HOW MUCH they disagree or the QUALITY
of the disagreeing sensors. That has problems:

  1. Two high-quality sensors disagreeing should hurt confidence more
     than one low-quality sensor disagreeing with two high-quality ones.

  2. The flat 0.8 has no theoretical basis. A reviewer will ask "why 0.8?"
     and there's no answer.

This module computes a weighted disagreement penalty based on the
weighted entropy of the detection distribution.

Formulation
-----------
Let p = (sum of weights of detecting sensors) / (total weight).
Let H(p) = -p*log2(p) - (1-p)*log2(1-p) be the binary entropy.
H(p) is 0 when all sensors agree (p = 0 or 1) and 1.0 at maximum
disagreement (p = 0.5).

Penalty = 1 - alpha * H(p), where alpha in [0, 1] controls how harshly
disagreement is punished. alpha=0 disables the penalty; alpha=0.4
recovers approximately the legacy 0.8 multiplier at maximum disagreement,
but smoothly scales for partial disagreement.

This is interpretable, parameterizable, and grounded in information theory.
"""

from __future__ import annotations
import math


def binary_entropy(p: float) -> float:
    """
    Binary Shannon entropy in bits. H(0) = H(1) = 0; H(0.5) = 1.
    """
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def weighted_disagreement_penalty(
    positive_weight: float,
    total_weight: float,
    alpha: float = 0.4,
) -> float:
    """
    Compute a disagreement penalty multiplier in (1 - alpha, 1.0].

    Parameters
    ----------
    positive_weight : sum of weights of sensors reporting detected=True
    total_weight    : sum of all sensor weights
    alpha           : penalty strength in [0, 1]

    Returns
    -------
    Multiplier to apply to the raw weighted detection score.

    Examples
    --------
    All agree (p=1):     penalty = 1.0
    All disagree (p=0):  penalty = 1.0  (no positive sensors, but unanimous)
    Half/half (p=0.5):   penalty = 1 - alpha
    Mostly agree (p=0.8): penalty = 1 - alpha * 0.72
    """
    if total_weight <= 0:
        return 1.0
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha must be in [0, 1], got {alpha}")
    p = positive_weight / total_weight
    h = binary_entropy(p)
    return max(0.0, 1.0 - alpha * h)


def legacy_flat_penalty(disagreement: bool) -> float:
    """Legacy flat 0.8 penalty when ANY disagreement exists. Kept for backwards-compat."""
    return 0.8 if disagreement else 1.0
