def compute_confidence(fusion_result, sensor_data):
    """
    Confidence assessment built on top of weighted fusion.
    """
    weighted_score = fusion_result["weighted_detection_score"]
    avg_quality = fusion_result["avg_quality"]
    avg_latency = fusion_result["avg_latency"]
    disagreement = fusion_result["disagreement"]

    reasons = []
    actions = []

    low_quality_sensors = [s["sensor"] for s in sensor_data if s["quality"] < 0.5]
    medium_quality_sensors = [
        s["sensor"] for s in sensor_data if 0.5 <= s["quality"] < 0.7
    ]
    high_latency_sensors = [s["sensor"] for s in sensor_data if s["latency"] > 400]

    if disagreement:
        reasons.append("sensor disagreement detected")
        actions.append("request alternate confirmation source")

    if low_quality_sensors:
        reasons.append(f"low sensor quality in: {', '.join(low_quality_sensors)}")
        actions.append(f"monitor degraded sensor(s): {', '.join(low_quality_sensors)}")
    elif medium_quality_sensors:
        reasons.append(
            f"moderate quality degradation in: {', '.join(medium_quality_sensors)}"
        )

    if high_latency_sensors:
        reasons.append(f"high latency in: {', '.join(high_latency_sensors)}")
        actions.append(f"re-check delayed sensor(s): {', '.join(high_latency_sensors)}")

    # Confidence classification tied to weighted fusion + degradation context
    if (
        weighted_score >= 0.8
        and avg_quality >= 0.8
        and avg_latency < 200
        and not disagreement
    ):
        level = "HIGH"
    elif weighted_score >= 0.5 and avg_quality >= 0.55 and avg_latency < 450:
        level = "MEDIUM"
    else:
        level = "LOW"

    if level == "HIGH" and not reasons:
        reasons.append("all sensors aligned within acceptable bounds")
        actions.append("continue normal monitoring")
    elif level == "MEDIUM" and "continue normal monitoring" not in actions:
        actions.append("increase observation frequency")
    elif level == "LOW":
        actions.append("treat fused output as degraded and seek external validation")

    return {
        "level": level,
        "weighted_score": round(weighted_score, 3),
        "reasons": reasons,
        "actions": actions,
    }