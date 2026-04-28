import copy


def degrade_sensor(sensor, quality_drop=0.0, latency_increase=0.0, detected=None):
    """
    Return a degraded copy of a sensor reading.

    Parameters:
    - quality_drop: amount to reduce quality by
    - latency_increase: amount to add to latency
    - detected: optional forced detection override
    """
    updated = copy.deepcopy(sensor)

    updated["quality"] = max(0.0, round(updated["quality"] - quality_drop, 3))
    updated["latency"] = round(updated["latency"] + latency_increase, 1)

    if detected is not None:
        updated["detected"] = bool(detected)

    return updated


def degrade_step(sensor_step, degradation_rules):
    """
    Apply degradation rules to a list of sensor readings for one time step.

    degradation_rules format:
    {
        "SensorA": {"quality_drop": 0.2, "latency_increase": 150, "detected": False},
        "SensorB": {"quality_drop": 0.1}
    }
    """
    degraded_step = []

    for sensor in sensor_step:
        sensor_name = sensor["sensor"]
        if sensor_name in degradation_rules:
            rule = degradation_rules[sensor_name]
            degraded_sensor = degrade_sensor(
                sensor,
                quality_drop=rule.get("quality_drop", 0.0),
                latency_increase=rule.get("latency_increase", 0.0),
                detected=rule.get("detected"),
            )
            degraded_step.append(degraded_sensor)
        else:
            degraded_step.append(copy.deepcopy(sensor))

    return degraded_step


def build_conflict_step(base_step, target_sensor, forced_detection):
    """
    Force one sensor into disagreement for testing conflict behavior.
    """
    return degrade_step(
        base_step,
        {
            target_sensor: {
                "detected": forced_detection
            }
        }
    )