"""
Sensor degradation utilities for scenario construction and testing.
"""

import copy


def degrade_sensor(
    sensor: dict,
    quality_drop: float = 0.0,
    latency_increase: float = 0.0,
    detected: bool | None = None,
) -> dict:
    """Return a degraded copy of a sensor reading."""
    s = copy.deepcopy(sensor)
    s["quality"] = max(0.0, round(s["quality"] - quality_drop, 3))
    s["latency"] = round(s["latency"] + latency_increase, 1)
    if detected is not None:
        s["detected"] = bool(detected)
    return s


def degrade_step(sensor_step: list, degradation_rules: dict) -> list:
    """
    Apply per-sensor degradation rules to one time step.

    degradation_rules format:
    {
        "SensorA": {"quality_drop": 0.2, "latency_increase": 150, "detected": False},
    }
    """
    result = []
    for sensor in sensor_step:
        rule = degradation_rules.get(sensor["sensor"])
        if rule:
            result.append(degrade_sensor(
                sensor,
                quality_drop=rule.get("quality_drop", 0.0),
                latency_increase=rule.get("latency_increase", 0.0),
                detected=rule.get("detected"),
            ))
        else:
            result.append(copy.deepcopy(sensor))
    return result


def build_conflict_step(base_step: list, target_sensor: str, forced_detection: bool) -> list:
    """Force one sensor into disagreement — for testing conflict/spoof behaviour."""
    return degrade_step(base_step, {target_sensor: {"detected": forced_detection}})
