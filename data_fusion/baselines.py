"""
Naive baseline fusion methods for benchmarking.

These are intentionally simple — they exist to quantify where
confidence-weighted fusion adds value over naive approaches.

All methods return the same output schema as fuse_sensors() so
they can be compared directly in the experiment runner.
"""


def _empty_result() -> dict:
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


def simple_average(sensor_data: list, **_) -> dict:
    """
    Baseline 1: Unweighted average.

    All sensors contribute equally regardless of quality, latency,
    or reliability history. Detection threshold: score >= 0.5.

    Weakness: treats a degraded sensor the same as a healthy one.
    """
    if not sensor_data:
        return _empty_result()

    detections = [bool(s["detected"]) for s in sensor_data]
    qualities = [float(s["quality"]) for s in sensor_data]
    latencies = [float(s["latency"]) for s in sensor_data]

    score = sum(detections) / len(detections)

    return {
        "detected_count": sum(detections),
        "avg_quality": round(sum(qualities) / len(qualities), 3),
        "avg_latency": round(sum(latencies) / len(latencies), 1),
        "raw_weighted_detection_score": round(score, 3),
        "weighted_detection_score": round(score, 3),
        "fused_detection": score >= 0.5,
        "per_sensor_weights": {
            s["sensor"]: {"final_weight": 1.0, "detected": bool(s["detected"])}
            for s in sensor_data
        },
        "disagreement": len(set(detections)) > 1,
        "disagreement_penalty": 1.0,
    }


def majority_vote(sensor_data: list, **_) -> dict:
    """
    Baseline 2: Majority vote.

    Detection is True if more than half of sensors detect the target.
    No weights. Ties (even split) resolve to False.

    Weakness: ignores all quality and latency information.
    """
    if not sensor_data:
        return _empty_result()

    detections = [bool(s["detected"]) for s in sensor_data]
    qualities = [float(s["quality"]) for s in sensor_data]
    latencies = [float(s["latency"]) for s in sensor_data]

    count = sum(detections)
    fused = count > len(detections) / 2
    score = count / len(detections)

    return {
        "detected_count": count,
        "avg_quality": round(sum(qualities) / len(qualities), 3),
        "avg_latency": round(sum(latencies) / len(latencies), 1),
        "raw_weighted_detection_score": round(score, 3),
        "weighted_detection_score": round(score, 3),
        "fused_detection": fused,
        "per_sensor_weights": {
            s["sensor"]: {"final_weight": 1.0, "detected": bool(s["detected"])}
            for s in sensor_data
        },
        "disagreement": len(set(detections)) > 1,
        "disagreement_penalty": 1.0,
    }


def best_quality_only(sensor_data: list, **_) -> dict:
    """
    Baseline 3: Trust only the highest-quality sensor.

    Ignores all other sensors entirely.

    Weakness: ignores latency and reliability; a single degraded sensor
    with slightly higher quality can dominate incorrectly.
    """
    if not sensor_data:
        return _empty_result()

    best = max(sensor_data, key=lambda s: float(s["quality"]))
    detections = [bool(s["detected"]) for s in sensor_data]
    qualities = [float(s["quality"]) for s in sensor_data]
    latencies = [float(s["latency"]) for s in sensor_data]

    fused = bool(best["detected"])
    score = 1.0 if fused else 0.0

    return {
        "detected_count": sum(detections),
        "avg_quality": round(sum(qualities) / len(qualities), 3),
        "avg_latency": round(sum(latencies) / len(latencies), 1),
        "raw_weighted_detection_score": round(score, 3),
        "weighted_detection_score": round(score, 3),
        "fused_detection": fused,
        "per_sensor_weights": {
            s["sensor"]: {
                "final_weight": 1.0 if s["sensor"] == best["sensor"] else 0.0,
                "detected": bool(s["detected"]),
            }
            for s in sensor_data
        },
        "disagreement": len(set(detections)) > 1,
        "disagreement_penalty": 1.0,
    }
