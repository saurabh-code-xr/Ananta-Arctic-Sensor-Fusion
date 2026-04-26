"""
Per-sensor reliability memory.

Tracks historical quality * freshness samples per sensor and
returns a bounded reliability factor fed back into the fusion core.
"""

from data_fusion.utils import freshness_factor
from data_fusion.logger import get_logger

logger = get_logger("reliability")

_DEFAULT_BANDS = [
    (0.8, 1.0),
    (0.6, 0.9),
    (0.4, 0.75),
    (0.0, 0.6),
]


def update_reliability_history(history: dict, sensor_data: list, config: dict | None = None) -> dict:
    """
    Append a reliability sample for each sensor in the current time step.

    reliability_sample = quality * freshness_factor(latency)
    """
    for sensor in sensor_data:
        name = sensor["sensor"]
        quality = float(sensor["quality"])
        latency = float(sensor["latency"])
        sample = quality * freshness_factor(latency, config=config)
        history.setdefault(name, []).append(sample)
        logger.debug("Reliability sample for %s: %.3f (q=%.2f, l=%.0f)", name, sample, quality, latency)
    return history


def get_reliability_factor(history: dict, sensor_name: str, config: dict | None = None) -> float:
    """
    Return a historical reliability factor for a sensor.

    Defaults to 1.0 for sensors with no prior history (benefit of the doubt).
    Bounded to [0.6, 1.0] to prevent any sensor from being fully excluded.
    """
    samples = history.get(sensor_name, [])
    if not samples:
        return 1.0

    avg = sum(samples) / len(samples)

    bands = _DEFAULT_BANDS
    if config:
        raw = config.get("fusion", {}).get("reliability_bands", [])
        if raw:
            bands = [(b["min_avg"], b["factor"]) for b in raw]

    for min_avg, factor in bands:
        if avg >= min_avg:
            logger.debug("Reliability factor for %s: %.2f (avg=%.3f)", sensor_name, factor, avg)
            return factor

    return bands[-1][1]
