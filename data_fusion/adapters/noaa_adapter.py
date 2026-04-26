"""
NOAA Climate Data Online adapter.

Fetches real weather station data from NOAA's public API and converts it
into the canonical sensor reading format for validation on real-world data.

NOAA CDO API is free and does not require payment.
Get a free token at: https://www.ncdc.noaa.gov/cdo-web/token

What we map from NOAA data:
  - Temperature deviation from normal  → quality signal (bigger deviation = lower quality)
  - Wind speed                          → latency proxy (higher wind = higher sensor stress)
  - Precipitation                       → detection (precipitation event = environmental degradation)
  - Station ID                          → sensor name

This is a creative mapping — not literal sensor data, but it provides
real-world environmental stress patterns that model degraded sensing conditions.
"""

import os
import time
from datetime import datetime, timedelta

from data_fusion.adapters.base import SensorAdapter
from data_fusion.logger import get_logger

logger = get_logger("adapter.noaa")

NOAA_BASE_URL = "https://www.ncdc.noaa.gov/cdo-web/api/v2"


class NOAAAdapter(SensorAdapter):
    """
    Fetch real weather station data from NOAA CDO API.

    Maps weather observations into sensor reading format:
      - Multiple stations in a region → multiple sensors
      - Temperature, wind, precipitation → quality/latency/detected signals
    """

    def __init__(
        self,
        station_ids: list[str],
        token: str | None = None,
        lookback_days: int = 30,
        dataset_id: str = "GHCND",
    ):
        """
        Parameters
        ----------
        station_ids  : list of NOAA station IDs (e.g. ['GHCND:USW00094728'])
        token        : NOAA CDO API token (or set NOAA_TOKEN env var)
        lookback_days: how many days of historical data to fetch
        dataset_id   : NOAA dataset (GHCND = Global Historical Climatology Network Daily)
        """
        self.station_ids = station_ids
        self.token = token or os.environ.get("NOAA_TOKEN", "")
        self.lookback_days = lookback_days
        self.dataset_id = dataset_id

        if not self.token:
            logger.warning(
                "No NOAA token set. Get a free token at https://www.ncdc.noaa.gov/cdo-web/token "
                "and set it in config.yaml (sensors.noaa.token) or NOAA_TOKEN env var."
            )

    def fetch(self) -> list[list[dict]]:
        """
        Fetch NOAA daily observations and convert to time steps.

        Each day becomes one time step; each station becomes one sensor.
        """
        try:
            import requests
        except ImportError:
            logger.error("requests library not installed. Run: pip install requests")
            return []

        if not self.token:
            logger.error("NOAA token required. Returning empty dataset.")
            return []

        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.lookback_days)

        headers = {"token": self.token}
        params = {
            "datasetid": self.dataset_id,
            "stationid": self.station_ids,
            "startdate": start_date.strftime("%Y-%m-%d"),
            "enddate": end_date.strftime("%Y-%m-%d"),
            "datatypeid": ["TMAX", "TMIN", "PRCP", "AWND"],
            "limit": 1000,
            "units": "metric",
        }

        try:
            response = requests.get(f"{NOAA_BASE_URL}/data", headers=headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error("NOAA API request failed: %s", e)
            return []

        results = data.get("results", [])
        if not results:
            logger.warning("NOAA returned no data for stations %s over %d days.", self.station_ids, self.lookback_days)
            return []

        logger.info("NOAA returned %d observations for %d stations.", len(results), len(self.station_ids))
        return self._convert_to_steps(results)

    def _convert_to_steps(self, observations: list[dict]) -> list[list[dict]]:
        """
        Group observations by date into time steps.
        Each date = one time step; each station = one sensor reading.
        """
        by_date: dict[str, dict[str, dict]] = {}

        for obs in observations:
            date = obs["date"][:10]  # YYYY-MM-DD
            station = obs["station"]
            datatype = obs["datatype"]
            value = float(obs["value"])

            by_date.setdefault(date, {}).setdefault(station, {})
            by_date[date][station][datatype] = value

        steps = []
        for date in sorted(by_date.keys()):
            step = []
            for station, readings in by_date[date].items():
                reading = self._readings_to_sensor(station, readings)
                step.append(reading)
            if step:
                steps.append(step)

        logger.info("Converted NOAA data to %d time steps.", len(steps))
        return steps

    def _readings_to_sensor(self, station_id: str, readings: dict) -> dict:
        """
        Map NOAA daily observations to sensor reading format.

        quality  : derived from temperature range (larger swing = less stable = lower quality)
        latency  : derived from wind speed (higher wind = harder to measure = higher effective latency)
        detected : True if precipitation recorded (environmental stress event detected)
        """
        tmax = readings.get("TMAX", 0.0)
        tmin = readings.get("TMIN", 0.0)
        prcp = readings.get("PRCP", 0.0)
        awnd = readings.get("AWND", 0.0)  # average wind speed m/s

        # Temperature range → quality proxy (normalize 0-30°C range to 1.0-0.2)
        temp_range = abs(tmax - tmin)
        quality = max(0.1, round(1.0 - (temp_range / 35.0), 3))

        # Wind speed → latency proxy (0 m/s = 100ms, 30 m/s = 700ms)
        latency = round(100 + (awnd / 30.0) * 600, 1)

        # Precipitation > 0 → environmental event detected
        detected = prcp > 0.0

        name = station_id.split(":")[-1] if ":" in station_id else station_id

        return {
            "sensor": name,
            "detected": detected,
            "quality": quality,
            "latency": latency,
        }


def build_noaa_adapter_from_config(config: dict) -> "NOAAAdapter":
    """Convenience constructor that reads from config.yaml sensors.noaa section."""
    noaa_cfg = config.get("sensors", {}).get("noaa", {})
    station_id = noaa_cfg.get("station_id", "GHCND:USW00094728")
    token = noaa_cfg.get("token") or os.environ.get("NOAA_TOKEN", "")
    lookback_days = noaa_cfg.get("lookback_days", 30)
    return NOAAAdapter(
        station_ids=[station_id],
        token=token,
        lookback_days=lookback_days,
    )
