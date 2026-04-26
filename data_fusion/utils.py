"""
Shared utility functions used across fusion and reliability modules.
"""

from data_fusion.logger import get_logger

logger = get_logger("utils")

# Built-in defaults — overridden by config.yaml freshness_brackets
_DEFAULT_BRACKETS = [
    (100,  1.0),
    (200,  0.9),
    (300,  0.75),
    (400,  0.55),
    (600,  0.35),
    (99999, 0.2),
]


def freshness_factor(latency_ms: float, config: dict | None = None) -> float:
    """
    Convert sensor latency into a 0..1 freshness weight.

    Lower latency = higher freshness = more trusted reading.
    Brackets are tunable via config.yaml (fusion.freshness_brackets).
    """
    if latency_ms < 0:
        logger.warning("Negative latency %.1f received — clamping to 0.", latency_ms)
        latency_ms = 0.0

    brackets = _DEFAULT_BRACKETS
    if config:
        raw = config.get("fusion", {}).get("freshness_brackets", [])
        if raw:
            brackets = [(b["max_latency_ms"], b["factor"]) for b in raw]

    for max_ms, factor in brackets:
        if latency_ms <= max_ms:
            return factor
    return brackets[-1][1]


def validate_sensor_reading(sensor: dict) -> list[str]:
    """
    Validate one sensor reading dict.
    Returns a list of error strings (empty = valid).
    """
    errors = []
    required = {"sensor", "detected", "quality", "latency"}
    missing = required - set(sensor.keys())
    if missing:
        errors.append(f"missing fields: {missing}")
        return errors  # can't validate further without required fields

    if not isinstance(sensor["sensor"], str) or not sensor["sensor"].strip():
        errors.append("sensor name must be a non-empty string")

    try:
        quality = float(sensor["quality"])
        if not 0.0 <= quality <= 1.0:
            errors.append(f"quality {quality} out of range [0, 1]")
    except (TypeError, ValueError):
        errors.append(f"quality must be numeric, got {type(sensor['quality'])}")

    try:
        latency = float(sensor["latency"])
        if latency < 0:
            errors.append(f"latency {latency} must be >= 0")
    except (TypeError, ValueError):
        errors.append(f"latency must be numeric, got {type(sensor['latency'])}")

    return errors


def validate_sensor_list(sensor_data: list) -> None:
    """
    Validate a list of sensor readings.
    Logs warnings for bad readings and raises ValueError if list is malformed.
    """
    if not isinstance(sensor_data, list):
        raise ValueError(f"sensor_data must be a list, got {type(sensor_data)}")
    for i, sensor in enumerate(sensor_data):
        errors = validate_sensor_reading(sensor)
        if errors:
            logger.warning("Sensor reading [%d] has issues: %s", i, "; ".join(errors))
