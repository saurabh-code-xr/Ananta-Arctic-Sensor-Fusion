"""
OpenWeatherMap adapter.

Fetches live weather data from OpenWeatherMap's free API tier and maps
it into sensor reading format for real-time demonstration.

Free tier: 60 calls/minute, no credit card required.
Sign up at: https://openweathermap.org/api

What we map from OWM data:
  - Visibility     → quality (lower visibility = degraded sensing = lower quality)
  - Wind speed     → latency proxy
  - Weather code   → detected (adverse conditions = detection event)
  - City/station   → sensor name
"""

import os
from data_fusion.adapters.base import SensorAdapter
from data_fusion.logger import get_logger

logger = get_logger("adapter.openweather")

OWM_BASE_URL = "https://api.openweathermap.org/data/2.5"


class OpenWeatherAdapter(SensorAdapter):
    """
    Fetch current weather from multiple locations and convert to sensor readings.

    Each location = one sensor. Fetch multiple cities near your target region
    to simulate a multi-sensor network.
    """

    def __init__(
        self,
        locations: list[dict],
        api_key: str | None = None,
        units: str = "metric",
    ):
        """
        Parameters
        ----------
        locations : list of {name, lat, lon} dicts
        api_key   : OWM API key (or set OPENWEATHER_API_KEY env var)
        units     : "metric" | "imperial"
        """
        self.locations = locations
        self.api_key = api_key or os.environ.get("OPENWEATHER_API_KEY", "")
        self.units = units

        if not self.api_key:
            logger.warning(
                "No OpenWeatherMap API key set. "
                "Get a free key at https://openweathermap.org/api "
                "and set OPENWEATHER_API_KEY env var or config.yaml."
            )

    def fetch(self) -> list[list[dict]]:
        """
        Fetch current weather for all locations.
        Returns a single time step (current moment) as a one-element list.
        """
        try:
            import requests
        except ImportError:
            logger.error("requests library not installed. Run: pip install requests")
            return []

        if not self.api_key:
            logger.error("OpenWeatherMap API key required.")
            return []

        readings = []
        for loc in self.locations:
            reading = self._fetch_location(requests, loc)
            if reading:
                readings.append(reading)

        if not readings:
            return []

        logger.info("OpenWeather fetched %d location readings.", len(readings))
        return [readings]  # one time step

    def _fetch_location(self, requests, loc: dict) -> dict | None:
        params = {
            "lat": loc["lat"],
            "lon": loc["lon"],
            "appid": self.api_key,
            "units": self.units,
        }
        try:
            response = requests.get(f"{OWM_BASE_URL}/weather", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return self._convert(loc["name"], data)
        except Exception as e:
            logger.error("OpenWeather request failed for %s: %s", loc.get("name"), e)
            return None

    def _convert(self, name: str, data: dict) -> dict:
        """
        Map OWM response to sensor reading.

        quality  : visibility (0-10000m → 1.0-0.1)
        latency  : wind speed (0-30 m/s → 100-700ms)
        detected : adverse weather (rain, snow, fog, storm)
        """
        visibility = data.get("visibility", 10000)
        wind_speed = data.get("wind", {}).get("speed", 0.0)
        weather_id = data.get("weather", [{}])[0].get("id", 800)

        quality = max(0.1, round(visibility / 10000.0, 3))
        latency = round(100 + (min(wind_speed, 30) / 30.0) * 600, 1)

        # OWM codes: 2xx=thunderstorm, 3xx=drizzle, 5xx=rain, 6xx=snow, 7xx=atmosphere(fog/haze)
        adverse_codes = range(200, 800)
        detected = weather_id in adverse_codes

        return {
            "sensor": name,
            "detected": detected,
            "quality": quality,
            "latency": latency,
        }


def build_openweather_adapter_from_config(config: dict) -> "OpenWeatherAdapter":
    """Convenience constructor from config.yaml sensors.openweather section."""
    cfg = config.get("sensors", {}).get("openweather", {})
    api_key = cfg.get("api_key") or os.environ.get("OPENWEATHER_API_KEY", "")
    lat = cfg.get("lat", 68.3)
    lon = cfg.get("lon", 18.9)
    units = cfg.get("units", "metric")
    return OpenWeatherAdapter(
        locations=[{"name": "primary", "lat": lat, "lon": lon}],
        api_key=api_key,
        units=units,
    )
