"""
Confidence evaluation engine.

Interprets fusion outputs into operator-facing confidence levels:
  HIGH / MEDIUM / LOW

All thresholds are tunable via config.yaml (confidence.thresholds).
"""

from data_fusion.logger import get_logger

logger = get_logger("confidence")

DEFAULT_THRESHOLDS = {
    "high_score": 0.8,
    "high_quality": 0.8,
    "high_latency_ceiling": 200,
    "medium_score": 0.5,
    "medium_quality": 0.55,
    "medium_latency_ceiling": 450,
    "low_quality_threshold": 0.5,
    "high_latency_threshold": 400,
}


def _thresholds_from_config(config: dict) -> dict:
    """Extract confidence thresholds from loaded config dict."""
    cfg = config.get("confidence", {})
    high = cfg.get("thresholds", {}).get("high", {})
    medium = cfg.get("thresholds", {}).get("medium", {})
    flags = cfg.get("sensor_flags", {})
    return {
        "high_score": high.get("min_score", DEFAULT_THRESHOLDS["high_score"]),
        "high_quality": high.get("min_quality", DEFAULT_THRESHOLDS["high_quality"]),
        "high_latency_ceiling": high.get("max_latency_ms", DEFAULT_THRESHOLDS["high_latency_ceiling"]),
        "medium_score": medium.get("min_score", DEFAULT_THRESHOLDS["medium_score"]),
        "medium_quality": medium.get("min_quality", DEFAULT_THRESHOLDS["medium_quality"]),
        "medium_latency_ceiling": medium.get("max_latency_ms", DEFAULT_THRESHOLDS["medium_latency_ceiling"]),
        "low_quality_threshold": flags.get("low_quality_threshold", DEFAULT_THRESHOLDS["low_quality_threshold"]),
        "high_latency_threshold": flags.get("high_latency_threshold", DEFAULT_THRESHOLDS["high_latency_threshold"]),
    }


def compute_confidence(
    fusion_result: dict,
    sensor_data: list,
    thresholds: dict | None = None,
    config: dict | None = None,
) -> dict:
    """
    Assess operator-facing confidence from fusion outputs.

    Priority order for thresholds:
      1. explicit thresholds parameter (highest — for tests/overrides)
      2. config dict
      3. DEFAULT_THRESHOLDS (built-in fallback)

    Parameters
    ----------
    fusion_result : output from fuse_sensors()
    sensor_data   : raw sensor readings for this step
    thresholds    : explicit threshold override dict
    config        : loaded config dict (from data_fusion.config.get())

    Returns
    -------
    dict with: level, weighted_score, reasons, actions
    """
    if thresholds is not None:
        t = {**DEFAULT_THRESHOLDS, **thresholds}
    elif config is not None:
        t = _thresholds_from_config(config)
    else:
        t = DEFAULT_THRESHOLDS

    score = fusion_result["weighted_detection_score"]
    avg_quality = fusion_result["avg_quality"]
    avg_latency = fusion_result["avg_latency"]
    disagreement = fusion_result["disagreement"]

    low_quality = [s["sensor"] for s in sensor_data if float(s["quality"]) < t["low_quality_threshold"]]
    medium_quality = [
        s["sensor"] for s in sensor_data
        if t["low_quality_threshold"] <= float(s["quality"]) < 0.7
    ]
    high_latency = [s["sensor"] for s in sensor_data if float(s["latency"]) > t["high_latency_threshold"]]

    reasons = []
    actions = []

    if disagreement:
        reasons.append("sensor disagreement detected")
        actions.append("request alternate confirmation source")

    if low_quality:
        reasons.append(f"low sensor quality: {', '.join(low_quality)}")
        actions.append(f"monitor degraded sensor(s): {', '.join(low_quality)}")
    elif medium_quality:
        reasons.append(f"moderate quality degradation: {', '.join(medium_quality)}")

    if high_latency:
        reasons.append(f"high latency: {', '.join(high_latency)}")
        actions.append(f"re-check delayed sensor(s): {', '.join(high_latency)}")

    if (
        score >= t["high_score"]
        and avg_quality >= t["high_quality"]
        and avg_latency < t["high_latency_ceiling"]
        and not disagreement
    ):
        level = "HIGH"
    elif (
        score >= t["medium_score"]
        and avg_quality >= t["medium_quality"]
        and avg_latency < t["medium_latency_ceiling"]
    ):
        level = "MEDIUM"
    else:
        level = "LOW"

    if level == "HIGH" and not reasons:
        reasons.append("all sensors aligned within acceptable bounds")
        actions.append("continue normal monitoring")
    elif level == "MEDIUM" and "continue normal monitoring" not in actions:
        actions.append("increase observation frequency")
    elif level == "LOW":
        actions.append("treat fused output as degraded — seek external validation")

    logger.debug("Confidence: %s (score=%.3f, quality=%.3f, latency=%.0f)", level, score, avg_quality, avg_latency)

    return {
        "level": level,
        "weighted_score": round(score, 3),
        "reasons": reasons,
        "actions": actions,
    }
