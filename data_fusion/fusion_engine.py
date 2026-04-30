"""
Confidence-weighted sensor fusion core.

Fuses heterogeneous sensor inputs using:
  weight = quality * freshness_factor(latency) * reliability_factor * adversarial_down_weight

A disagreement penalty is applied when sensors contradict each other.
All parameters are tunable via config.yaml.

Backwards-compatible upgrades (all opt-in via config):
  - fusion.freshness_continuous: switch from step-function brackets to
    continuous decay (exponential / linear / sigmoid).
  - fusion.weighted_disagreement: replace flat penalty with entropy-based
    weighted disagreement penalty.
  - fusion.adversarial_detection: residual-based outlier detection that
    down-weights sensors strongly disagreeing with the consensus.

When none of the new config keys are set, behavior is unchanged from
the original implementation.
"""

from data_fusion.utils import freshness_factor, validate_sensor_list
from data_fusion.freshness import freshness_continuous
from data_fusion.disagreement import weighted_disagreement_penalty
from data_fusion.adversarial import detect_outliers
from data_fusion.reliability_memory import get_reliability_factor
from data_fusion.logger import get_logger

logger = get_logger("fusion")


def _resolve_freshness(latency_ms: float, config: dict | None) -> float:
    """Pick continuous or bracket-based freshness depending on config."""
    if config and config.get("fusion", {}).get("freshness_continuous"):
        return freshness_continuous(latency_ms, config=config)
    return freshness_factor(latency_ms, config=config)


def fuse_sensors(
    sensor_data: list,
    reliability_history: dict | None = None,
    config: dict | None = None,
) -> dict:
    """
    Fuse a list of sensor readings into a single detection estimate.

    Parameters
    ----------
    sensor_data         : list of dicts — sensor, detected, quality, latency
    reliability_history : per-sensor reliability memory from previous steps
    config              : loaded config dict (from data_fusion.config.get())

    Returns
    -------
    dict with fusion outputs and per-sensor debug info. Includes new
    fields when adversarial detection is enabled:
      - adversarial_flags: per-sensor outlier diagnostic
      - adversarial_active: True when at least one sensor was flagged
    """
    if reliability_history is None:
        reliability_history = {}

    validate_sensor_list(sensor_data)

    if not sensor_data:
        logger.warning("fuse_sensors called with empty sensor list — returning safe defaults.")
        return {
            "detected_count": 0,
            "avg_quality": 0.0,
            "avg_latency": 0.0,
            "raw_weighted_detection_score": 0.0,
            "weighted_detection_score": 0.0,
            "fused_detection": False,
            "per_sensor_weights": {},
            "disagreement": False,
            "disagreement_penalty": 1.0,
            "adversarial_flags": {},
            "adversarial_active": False,
        }

    cfg_fusion = (config or {}).get("fusion", {})
    detection_threshold = cfg_fusion.get("detection_threshold", 0.6)
    legacy_penalty_value = cfg_fusion.get("disagreement_penalty", 0.8)
    weighted_dis_cfg = cfg_fusion.get("weighted_disagreement", {})
    adversarial_cfg = cfg_fusion.get("adversarial_detection", {})

    detections = [bool(s["detected"]) for s in sensor_data]
    qualities = [float(s["quality"]) for s in sensor_data]
    latencies = [float(s["latency"]) for s in sensor_data]

    detected_count = sum(detections)
    avg_quality = sum(qualities) / len(qualities)
    avg_latency = sum(latencies) / len(latencies)
    disagreement = len(set(detections)) > 1

    # Adversarial detection (opt-in)
    adversarial_active = False
    if adversarial_cfg.get("enabled", False):
        flags = detect_outliers(
            sensor_data,
            suspect_threshold=adversarial_cfg.get("suspect_threshold", 0.7),
            quality_floor=adversarial_cfg.get("quality_floor", 0.6),
        )
        adversarial_active = any(f["suspect"] for f in flags.values())
    else:
        flags = {s["sensor"]: {"suspect": False, "down_weight": 1.0,
                                "consensus_disagrees": False,
                                "consensus_score_against": 0.0}
                 for s in sensor_data}

    per_sensor_weights = {}
    total_weight = 0.0
    positive_weight = 0.0

    for sensor in sensor_data:
        name = sensor["sensor"]
        quality = float(sensor["quality"])
        latency = float(sensor["latency"])
        detected = bool(sensor["detected"])

        freshness = _resolve_freshness(latency, config)
        reliability = get_reliability_factor(reliability_history, name, config=config)
        adversarial_dw = flags.get(name, {}).get("down_weight", 1.0)

        weight = quality * freshness * reliability * adversarial_dw

        per_sensor_weights[name] = {
            "quality": round(quality, 3),
            "latency": latency,
            "freshness_factor": round(freshness, 3),
            "reliability_factor": round(reliability, 3),
            "adversarial_down_weight": round(adversarial_dw, 3),
            "final_weight": round(weight, 3),
            "detected": detected,
            "suspect": flags.get(name, {}).get("suspect", False),
        }

        total_weight += weight
        if detected:
            positive_weight += weight

    raw_score = positive_weight / total_weight if total_weight > 0 else 0.0

    # Disagreement penalty: weighted (entropy-based) if enabled, else legacy flat
    if weighted_dis_cfg.get("enabled", False):
        alpha = weighted_dis_cfg.get("alpha", 0.4)
        penalty = weighted_disagreement_penalty(positive_weight, total_weight, alpha=alpha)
    else:
        penalty = legacy_penalty_value if disagreement else 1.0

    weighted_score = raw_score * penalty
    fused_detection = weighted_score >= detection_threshold

    logger.debug(
        "Fusion: raw=%.3f penalty=%.3f final=%.3f detected=%s disagreement=%s adversarial=%s",
        raw_score, penalty, weighted_score, fused_detection, disagreement, adversarial_active,
    )

    return {
        "detected_count": detected_count,
        "avg_quality": round(avg_quality, 3),
        "avg_latency": round(avg_latency, 1),
        "raw_weighted_detection_score": round(raw_score, 3),
        "weighted_detection_score": round(weighted_score, 3),
        "fused_detection": fused_detection,
        "per_sensor_weights": per_sensor_weights,
        "disagreement": disagreement,
        "disagreement_penalty": round(penalty, 3),
        "adversarial_flags": flags,
        "adversarial_active": adversarial_active,
    }
