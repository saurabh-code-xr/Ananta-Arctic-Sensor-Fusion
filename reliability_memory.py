def update_reliability_history(history, sensor_data):
    """
    Update per-sensor reliability history using the current time step.

    Reliability is approximated using:
    reliability_sample = quality * freshness_factor

    We use latency thresholds similar to fusion_engine.py.
    """
    for sensor in sensor_data:
        sensor_name = sensor["sensor"]
        quality = float(sensor["quality"])
        latency = float(sensor["latency"])

        if latency <= 100:
            freshness = 1.0
        elif latency <= 200:
            freshness = 0.9
        elif latency <= 300:
            freshness = 0.75
        elif latency <= 400:
            freshness = 0.55
        elif latency <= 600:
            freshness = 0.35
        else:
            freshness = 0.2

        reliability_sample = quality * freshness

        if sensor_name not in history:
            history[sensor_name] = []

        history[sensor_name].append(reliability_sample)

    return history


def get_reliability_factor(history, sensor_name):
    """
    Return a historical reliability factor for a sensor.
    Uses the average of past reliability samples.
    """
    samples = history.get(sensor_name, [])
    if not samples:
        return 1.0

    avg_reliability = sum(samples) / len(samples)

    # Keep the factor bounded so it helps but does not dominate
    if avg_reliability >= 0.8:
        return 1.0
    elif avg_reliability >= 0.6:
        return 0.9
    elif avg_reliability >= 0.4:
        return 0.75
    else:
        return 0.6