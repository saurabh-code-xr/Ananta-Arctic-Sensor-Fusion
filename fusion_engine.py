from reliability_memory import get_reliability_factor


def _freshness_factor(latency_ms: float) -> float:
    """
    Convert latency into a 0..1 freshness factor.
    Lower latency => higher freshness.
    """
    if latency_ms <= 100:
        return 1.0
    if latency_ms <= 200:
        return 0.9
    if latency_ms <= 300:
        return 0.75
    if latency_ms <= 400:
        return 0.55
    if latency_ms <= 600:
        return 0.35
    return 0.2


def fuse_sensors(sensor_data, reliability_history=None):
    """
    Confidence-weighted fusion with:
    - quality weighting
    - latency freshness weighting
    - disagreement penalty
    - historical reliability memory (V3)

    Each sensor contributes according to:
    weight = quality * freshness_factor(latency) * reliability_factor
    """
    if reliability_history is None:
        reliability_history = {}

    if not sensor_data:
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
        sensor_name = sensor["sensor"]
        quality = float(sensor["quality"])
        latency = float(sensor["latency"])
        detected = bool(sensor["detected"])

        freshness = _freshness_factor(latency)
        reliability_factor = get_reliability_factor(reliability_history, sensor_name)

        weight = quality * freshness * reliability_factor

        per_sensor_weights[sensor_name] = {
            "quality": round(quality, 3),
            "latency": latency,
            "freshness_factor": round(freshness, 3),
            "reliability_factor": round(reliability_factor, 3),
            "final_weight": round(weight, 3),
            "detected": detected,
        }

        total_weight += weight
        if detected:
            positive_weight += weight

    raw_weighted_detection_score = (
        positive_weight / total_weight if total_weight > 0 else 0.0
    )

    disagreement_penalty = 0.8 if disagreement else 1.0
    weighted_detection_score = raw_weighted_detection_score * disagreement_penalty

    fused_detection = weighted_detection_score >= 0.6

    return {
        "detected_count": detected_count,
        "avg_quality": round(avg_quality, 3),
        "avg_latency": round(avg_latency, 1),
        "raw_weighted_detection_score": round(raw_weighted_detection_score, 3),
        "weighted_detection_score": round(weighted_detection_score, 3),
        "fused_detection": fused_detection,
        "per_sensor_weights": per_sensor_weights,
        "disagreement": disagreement,
        "disagreement_penalty": disagreement_penalty,
    }