"""
OpenAQ air quality adapter.

Fetches real-time air quality measurements from OpenAQ's global sensor network.
Free API, no authentication required.

What we map from OpenAQ data:
  - PM2.5 concentration     → quality (higher pollution = lower quality)
  - PM10 concentration      → latency proxy
  - AQI level               → detected (poor air = environmental degradation detected)
  - Station location/name   → sensor name

OpenAQ provides measurements from thousands of real air quality monitors worldwide.
Great for validating multi-sensor fusion under real environmental stress.
"""

import os
from datetime import datetime
from data_fusion.adapters.base import SensorAdapter
from data_fusion.logger import get_logger

logger = get_logger("adapter.openaq")

OPENAQ_BASE_URL = "https://api.openaq.org/v2"


class OpenAQAdapter(SensorAdapter):
    """
    Fetch real-time air quality data from OpenAQ's global network.

    Each monitoring location = one sensor. PM2.5/PM10 levels map to quality/latency.
    """

    def __init__(
        self,
        countries: list[str] | None = None,
        limit: int = 10,
    ):
        """
        Parameters
        ----------
        countries : list of country codes (e.g. ['US', 'CA', 'NO'])
                    if None, fetches from all available locations
        limit     : max number of stations to fetch from
        """
        self.countries = countries or ["US"]
        self.limit = limit

    def fetch(self) -> list[list[dict]]:
        """
        Fetch latest air quality readings and convert to sensor format.

        Returns a single time step (current moment) with multiple sensors
        (one per monitoring location).
        """
        try:
            import requests
        except ImportError:
            logger.error("requests library not installed. Run: pip install requests")
            return []

        try:
            readings = []
            for country in self.countries:
                readings.extend(self._fetch_country(requests, country))

            if not readings:
                logger.warning("OpenAQ returned no data for countries %s", self.countries)
                return []

            logger.info("OpenAQ returned %d stations.", len(readings))
            return [readings]  # Single time step with all stations as sensors

        except Exception as e:
            logger.error("OpenAQ fetch failed: %s", e)
            return []

    def _fetch_country(self, requests, country: str) -> list[dict]:
        """Fetch latest measurements for stations in a country."""
        try:
            response = requests.get(
                f"{OPENAQ_BASE_URL}/latest",
                params={
                    "country": country,
                    "limit": self.limit,
                    "sort": "lastUpdated",
                    "order": "desc",
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning("OpenAQ request failed for country %s: %s", country, e)
            return []

        results = data.get("results", [])
        readings = []

        for result in results:
            reading = self._result_to_sensor(result)
            if reading:
                readings.append(reading)

        return readings

    def _result_to_sensor(self, result: dict) -> dict | None:
        """
        Map OpenAQ measurement to sensor reading format.

        quality  : normalized from PM2.5 (0 µg/m³ = 1.0, >100 µg/m³ = 0.1)
        latency  : proxy from PM10 (high PM10 = measurement difficulty)
        detected : True if PM2.5 > 35 µg/m³ (EPA unhealthy threshold)
        """
        measurements = result.get("measurements", [])
        if not measurements:
            return None

        # Extract PM2.5 and PM10
        pm25 = None
        pm10 = None
        for m in measurements:
            if m.get("parameter") == "pm25":
                pm25 = m.get("value", 0)
            elif m.get("parameter") == "pm10":
                pm10 = m.get("value", 0)

        if pm25 is None:
            return None

        # Quality: PM2.5 to quality mapping (0-100 µg/m³ maps to 1.0-0.1)
        quality = max(0.1, round(1.0 - (pm25 / 100.0), 3))

        # Latency proxy: PM10 increases effective measurement latency
        pm10_val = pm10 if pm10 is not None else pm25
        latency = round(100 + (pm10_val / 50.0) * 300, 1)

        # Detected: PM2.5 > 35.4 µg/m³ (EPA "Unhealthy for Sensitive Groups")
        detected = pm25 > 35.4

        location = result.get("location", "unknown")
        city = result.get("city", "")
        name = f"{city}/{location}" if city else location

        return {
            "sensor": name,
            "detected": detected,
            "quality": quality,
            "latency": latency,
        }


def build_openaq_adapter_from_config(config: dict) -> "OpenAQAdapter":
    """Convenience constructor that reads from config.yaml sensors.openaq section."""
    openaq_cfg = config.get("sensors", {}).get("openaq", {})
    countries = openaq_cfg.get("countries", ["US", "CA", "NO"])
    limit = openaq_cfg.get("limit", 10)
    return OpenAQAdapter(countries=countries, limit=limit)
