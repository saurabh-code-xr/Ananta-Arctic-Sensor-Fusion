"""
Confidence-weighted sensor fusion core.

Fuses heterogeneous sensor inputs using:
  weight = quality * freshness_factor(latency) * reliability_factor

A disagreement penalty is applied when sensors contradict each other.
All parameters are tunable via config.yaml.
"""

from data_fusion.utils import freshness_factor, validate_sensor_list
from data_fusion.reliability_memory import get_reliability_factor
from data_fusion.logger import get_logger

logger = get_logger("fusion")


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
    dict with fusion outputs and per-sensor debug info
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
        }

    cfg_fusion = (config or {}).get("fusion", {})
    detection_threshold = cfg_fusion.get("detection_threshold", 0.6)
    disagreement_penalty_value = cfg_fusion.get("disagreement_penalty", 0.8)

    detections = [bool(s["detected"]) for s in sensor_data]
    qualities = [float(s["quality"]) for s in sensor_data]
    latencies = [float(s["latency"]) for s in sensor_data]

    detected_count = sum(detections)
    avg_quality = sum(qualities) / len(qualities)
    avg_latency = sum(latencies) / len(latencies)
    disagreement = len(set(detections)) > 1

    per_sensor_weights = {}
    total_weight = 0.0
    positive_weight = 0.0

    for sensor in sensor_data:
        name = sensor["sensor"]
        quality = float(sensor["quality"])
        latency = float(sensor["latency"])
        detected = bool(sensor["detected"])

        freshness = freshness_factor(latency, config=config)
        reliability = get_reliability_factor(reliability_history, name, config=config)
        weight = quality * freshness * reliability

        per_sensor_weights[name] = {
            "quality": round(quality, 3),
            "latency": latency,
            "freshness_factor": round(freshness, 3),
            "reliability_factor": round(reliability, 3),
            "final_weight": round(weight, 3),
            "detected": detected,
        }

        total_weight += weight
        if detected:
            positive_weight += weight

    raw_score = positive_weight / total_weight if total_weight > 0 else 0.0
    penalty = disagreement_penalty_value if disagreement else 1.0
    weighted_score = raw_score * penalty
    fused_detection = weighted_score >= detection_threshold

    logger.debug(
        "Fusion: score=%.3f penalty=%.1f final=%.3f detected=%s disagreement=%s",
        raw_score, penalty, weighted_score, fused_detection, disagreement,
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
        "disagreement_penalty": penalty,
    }
