"""
Base adapter interface.

All sensor adapters must return data in the canonical sensor reading format:
    [
        {"sensor": "A", "detected": True, "quality": 0.85, "latency": 120},
        ...
    ]

Implement SensorAdapter and register it in adapter_factory.py.
"""

from abc import ABC, abstractmethod


class SensorAdapter(ABC):
    """Base class for all sensor data sources."""

    @abstractmethod
    def fetch(self) -> list[list[dict]]:
        """
        Fetch sensor data and return it as a list of time steps.

        Each time step is a list of sensor reading dicts:
            {"sensor": str, "detected": bool, "quality": float, "latency": float}
        """

    def validate(self, steps: list[list[dict]]) -> bool:
        """Basic structural check — override for stricter validation."""
        from data_fusion.utils import validate_sensor_reading
        for step in steps:
            for reading in step:
                if validate_sensor_reading(reading):
                    return False
        return True
