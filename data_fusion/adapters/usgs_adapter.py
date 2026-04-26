"""
USGS seismic/hazard adapter.

Fetches real-time earthquake data from USGS Earthquake Hazards Program.
Free API, no authentication required.

What we map from USGS earthquake data:
  - Earthquake magnitude   → quality (larger quakes = more signal = better quality)
  - Earthquake depth       → latency proxy (deep quakes harder to detect = higher latency)
  - Recent seismic events  → detected (earthquake detected = environmental event)
  - Region/location        → sensor name

This demonstrates degraded sensing under extreme environmental stress (seismic activity).
Great for validating fusion system behavior during rare high-energy events.
"""

from datetime import datetime, timedelta
from data_fusion.adapters.base import SensorAdapter
from data_fusion.logger import get_logger

logger = get_logger("adapter.usgs")

USGS_BASE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary"


class USGSAdapter(SensorAdapter):
    """
    Fetch real-time earthquake data from USGS Earthquake Hazards Program.

    Maps seismic measurements into sensor reading format for extreme event validation.
    """

    def __init__(
        self,
        min_magnitude: float = 4.5,
        time_range_hours: int = 24,
    ):
        """
        Parameters
        ----------
        min_magnitude     : minimum earthquake magnitude to include
        time_range_hours  : how many hours of historical data to fetch
        """
        self.min_magnitude = min_magnitude
        self.time_range_hours = time_range_hours

    def fetch(self) -> list[list[dict]]:
        """
        Fetch latest earthquake data and convert to sensor format.

        Returns a single time step (current moment) with earthquake events as sensors.
        """
        try:
            import requests
        except ImportError:
            logger.error("requests library not installed. Run: pip install requests")
            return []

        try:
            # USGS provides predefined feeds by magnitude range
            # Using "significant" (M4.5+) feed covers most seismic activity
            response = requests.get(
                f"{USGS_BASE_URL}/significant_month.geojson",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error("USGS API request failed: %s", e)
            return []

        features = data.get("features", [])
        if not features:
            logger.warning("USGS returned no earthquake data.")
            return []

        # Filter by time range and magnitude
        cutoff_time = datetime.utcnow() - timedelta(hours=self.time_range_hours)
        cutoff_timestamp = cutoff_time.timestamp() * 1000  # USGS uses milliseconds

        readings = []
        for feature in features:
            if feature.get("properties", {}).get("time", 0) < cutoff_timestamp:
                continue  # Outside our time range

            reading = self._feature_to_sensor(feature)
            if reading:
                readings.append(reading)

        if not readings:
            logger.warning(
                "USGS returned no earthquakes in range M%.1f+ in last %d hours.",
                self.min_magnitude,
                self.time_range_hours,
            )
            return []

        logger.info("USGS returned %d earthquakes.", len(readings))
        return [readings]  # Single time step

    def _feature_to_sensor(self, feature: dict) -> dict | None:
        """
        Map USGS GeoJSON feature to sensor reading format.

        quality  : normalized from magnitude (M4.5 = 0.5, M8+ = 1.0)
        latency  : proxy from depth (shallow = clearer = lower latency)
        detected : True if magnitude >= min_magnitude (earthquake detected)
        """
        props = feature.get("properties", {})
        mag = float(props.get("mag", 0))

        if mag < self.min_magnitude:
            return None

        depth_km = float(feature.get("geometry", {}).get("coordinates", [0, 0, 0])[2] or 0)

        # Quality: magnitude normalized to [0.1, 1.0]
        # M4.5 = 0.5, M8.0 = 1.0, >M8 = 1.0
        quality = max(0.1, min(1.0, round((mag - 3.5) / 4.5, 3)))

        # Latency proxy: depth in km affects measurement clarity
        # Shallow (<10km) = clearer = 150ms
        # Deep (>100km) = harder = 400ms
        latency = round(150 + (depth_km / 100.0) * 250, 1)

        # Always detected if we have this data (magnitude-filtered)
        detected = True

        title = props.get("title", "Unknown")
        place = props.get("place", "unknown")

        return {
            "sensor": f"USGS_{title}",
            "detected": detected,
            "quality": quality,
            "latency": latency,
        }


def build_usgs_adapter_from_config(config: dict) -> "USGSAdapter":
    """Convenience constructor that reads from config.yaml sensors.usgs section."""
    usgs_cfg = config.get("sensors", {}).get("usgs", {})
    min_magnitude = usgs_cfg.get("min_magnitude", 4.5)
    time_range_hours = usgs_cfg.get("time_range_hours", 24)
    return USGSAdapter(min_magnitude=min_magnitude, time_range_hours=time_range_hours)
