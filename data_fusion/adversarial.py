"""
Residual-based adversarial sensor detection.

The original system has an admitted vulnerability: a compromised sensor
that reports high quality but incorrect detections can mislead the fusion
output, because quality is self-reported and trusted.

This module adds a leave-one-out residual check:

  For each sensor S_i, compute the fused score WITHOUT S_i.
  Compare to S_i's reported detection.
  If S_i strongly disagrees with the consensus of all other sensors
  AND has reported high quality, flag S_i as suspect and down-weight it.

This is a standard technique in fault-tolerant sensor fusion (residual
generation, parity space methods). It cannot detect collusion (multiple
spoofed sensors agreeing with each other) but it materially improves
robustness against single-sensor spoofing — the scenario the original
README explicitly calls out as a weakness.

Reference: Hwang et al., "A Survey of Fault Detection, Isolation, and
Reconfiguration Methods" (IEEE TCST, 2010).
"""

from __future__ import annotations


def _consensus_without(sensor_data: list, exclude_name: str) -> tuple[float, float]:
    """
    Compute (positive_weight, total_weight) using simple quality-weighted vote
    of all sensors except the excluded one. Used as a quick consensus signal
    independent of the suspect sensor.
    """
    pos = 0.0
    total = 0.0
    for s in sensor_data:
        if s["sensor"] == exclude_name:
            continue
        q = float(s["quality"])
        total += q
        if bool(s["detected"]):
            pos += q
    return pos, total


def detect_outliers(
    sensor_data: list,
    suspect_threshold: float = 0.7,
    quality_floor: float = 0.6,
) -> dict[str, dict]:
    """
    Flag sensors that strongly disagree with the consensus of all others.

    A sensor is flagged when:
      - its reported quality is >= quality_floor (so it's claiming to be reliable)
      - the consensus of OTHER sensors strongly disagrees with it
        (consensus_score >= suspect_threshold for the OPPOSITE detection)

    Parameters
    ----------
    sensor_data : list of sensor reading dicts
    suspect_threshold : how strong the opposing consensus must be (0..1)
    quality_floor : minimum reported quality to consider a sensor "claiming reliability"

    Returns
    -------
    dict keyed by sensor name with diagnostic info:
        {
          "<sensor_name>": {
              "suspect": bool,
              "consensus_disagrees": bool,
              "consensus_score_against": float,  # how strongly others disagree
              "down_weight": float,  # multiplier in (0, 1] to apply
          },
          ...
        }
    """
    if len(sensor_data) < 3:
        # Need at least 3 sensors for a meaningful leave-one-out
        return {
            s["sensor"]: {
                "suspect": False,
                "consensus_disagrees": False,
                "consensus_score_against": 0.0,
                "down_weight": 1.0,
            }
            for s in sensor_data
        }

    flags: dict[str, dict] = {}
    for s in sensor_data:
        name = s["sensor"]
        s_detected = bool(s["detected"])
        s_quality = float(s["quality"])

        pos, total = _consensus_without(sensor_data, name)
        if total <= 0:
            consensus_score_for = 0.5
        else:
            consensus_score_for = pos / total

        # If this sensor says detected=True, the "score against" is the
        # consensus score for detected=False, and vice versa.
        consensus_score_against = (
            (1.0 - consensus_score_for) if s_detected else consensus_score_for
        )

        consensus_disagrees = consensus_score_against >= suspect_threshold
        suspect = consensus_disagrees and s_quality >= quality_floor

        # Down-weight scales with how strongly the consensus disagrees and
        # how confidently this sensor claims reliability.
        if suspect:
            # Linear interpolation: full trust at threshold, half trust at 1.0
            severity = (consensus_score_against - suspect_threshold) / max(
                1e-9, 1.0 - suspect_threshold
            )
            severity = max(0.0, min(1.0, severity))
            down_weight = 1.0 - 0.5 * severity
        else:
            down_weight = 1.0

        flags[name] = {
            "suspect": suspect,
            "consensus_disagrees": consensus_disagrees,
            "consensus_score_against": round(consensus_score_against, 3),
            "down_weight": round(down_weight, 3),
        }

    return flags
