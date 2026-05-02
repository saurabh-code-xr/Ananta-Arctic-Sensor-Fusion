"""
National Weather Service (NWS) adapter.

Fetches live weather observations from NWS stations and maps them into
the Ananta Meridian sensor reading format.

No API key or token required. Completely free and open.
API docs: https://www.weather.gov/documentation/services-web-api

What we map from NWS observation data:
  - Visibility       -> quality (low visibility = degraded sensing conditions)
  - Wind speed       -> latency proxy (high wind = harder to sense = higher latency)
  - Weather condition-> detected (adverse weather = environmental event detected)
  - Station ID       -> sensor name

Arctic stations used by default (relevant to Canadian Arctic sovereignty context):
  PABR - Barrow/Utqiagvik, Alaska (71.3N) -- northernmost NWS station
  PAOM - Nome, Alaska (64.5N)
  PAFA - Fairbanks, Alaska (64.8N)
  PACD - Cold Bay, Alaska (55.2N) -- Aleutian weather patterns

These stations model the same Arctic maritime environment as the Canadian
Arctic Archipelago scenario, providing a real-world environmental stress
signal to complement the synthetic AIS vessel data.
"""

import os
from data_fusion.adapters.base import SensorAdapter
from data_fusion.logger import get_logger

logger = get_logger("adapter.nws")

NWS_BASE_URL  = "https://api.weather.gov"
USER_AGENT    = "AnantaMeridian/0.3 SensorFusion (contact: github.com/saurabh-code-xr/Ananta-Arctic-Sensor-Fusion)"

# Default Arctic Alaska stations — publicly documented station IDs
DEFAULT_STATIONS = [
    {"id": "PABR", "name": "Barrow_AK",    "lat": 71.29, "lon": -156.79},
    {"id": "PAOM", "name": "Nome_AK",      "lat": 64.51, "lon": -165.43},
    {"id": "PAFA", "name": "Fairbanks_AK", "lat": 64.80, "lon": -147.86},
    {"id": "PACD", "name": "ColdBay_AK",   "lat": 55.20, "lon": -162.72},
]

# Weather condition codes that indicate adverse / degraded sensing conditions
# NWS uses plain-text present weather strings
_ADVERSE_KEYWORDS = {
    "fog", "mist", "snow", "blizzard", "storm", "thunder",
    "rain", "drizzle", "hail", "freezing", "ice", "smoke",
    "dust", "sand", "ash", "squall",
}


class NWSAdapter(SensorAdapter):
    """
    Fetch live Arctic weather observations from NWS and convert to sensor readings.

    Each station = one sensor. One time step per fetch (current moment).
    No authentication required.
    """

    def __init__(
        self,
        stations: list[dict] | None = None,
    ):
        """
        Parameters
        ----------
        stations : list of {id, name, lat, lon} dicts.
                   Defaults to four Arctic Alaska stations.
        """
        self.stations = stations or DEFAULT_STATIONS

    def fetch(self) -> list[list[dict]]:
        """
        Fetch latest observations from all configured stations.
        Returns a single time step (current moment) as a one-element list.
        """
        try:
            import requests
        except ImportError:
            logger.error("requests library not installed. Run: pip install requests")
            return []

        headers = {
            "User-Agent":    USER_AGENT,
            "Accept":        "application/geo+json",
            "Cache-Control": "no-cache",
        }

        readings = []
        for station in self.stations:
            reading = self._fetch_station(requests, station, headers)
            if reading:
                readings.append(reading)

        if not readings:
            logger.warning("NWS returned no usable data from any station.")
            return []

        logger.info("NWS fetched %d station readings.", len(readings))
        return [readings]   # one time step

    def _fetch_station(self, requests, station: dict, headers: dict) -> dict | None:
        """Fetch latest observation from a single NWS station."""
        url = f"{NWS_BASE_URL}/stations/{station['id']}/observations/latest"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning("NWS request failed for %s: %s", station["id"], e)
            return None

        props = data.get("properties", {})
        if not props:
            logger.warning("NWS: no properties in response for %s", station["id"])
            return None

        return self._convert(station["name"], props)

    def _convert(self, name: str, props: dict) -> dict | None:
        """
        Map NWS observation properties to sensor reading format.

        quality  : visibility (0-10000m -> 1.0-0.1). Low vis = degraded sensing.
        latency  : wind speed (0-30 m/s -> 100-700ms proxy).
        detected : True if any adverse weather present (fog, snow, storm, etc.)
        """
        # Visibility in metres (may be null)
        vis_val = props.get("visibility", {})
        visibility = vis_val.get("value") if isinstance(vis_val, dict) else None

        # Wind speed in km/h (NWS default) — convert to m/s
        wind_val = props.get("windSpeed", {})
        wind_kmh = wind_val.get("value") if isinstance(wind_val, dict) else None
        wind_ms  = (wind_kmh / 3.6) if wind_kmh is not None else 0.0

        # Present weather conditions (list of dicts with 'rawString')
        wx_list = props.get("presentWeather", []) or []
        wx_strings = " ".join(
            (w.get("rawString", "") or w.get("weather", "")).lower()
            for w in wx_list
            if isinstance(w, dict)
        )

        # Text description as fallback
        text_conditions = (props.get("textDescription") or "").lower()
        all_conditions  = f"{wx_strings} {text_conditions}"

        # Quality from visibility
        if visibility is not None and visibility >= 0:
            quality = max(0.1, round(min(visibility, 10000) / 10000.0, 3))
        else:
            quality = 0.5   # unknown visibility -> partial credit

        # Latency proxy from wind speed (0 m/s=100ms, 30+ m/s=700ms)
        latency = round(100.0 + (min(wind_ms, 30.0) / 30.0) * 600.0, 1)

        # Detection: any adverse weather keyword present
        detected = any(kw in all_conditions for kw in _ADVERSE_KEYWORDS)

        return {
            "sensor":   name,
            "detected": detected,
            "quality":  quality,
            "latency":  latency,
        }


def build_nws_adapter_from_config(config: dict) -> "NWSAdapter":
    """Convenience constructor from config.yaml sensors.nws section."""
    nws_cfg  = config.get("sensors", {}).get("nws", {})
    stations = nws_cfg.get("stations", None)   # None -> use defaults
    return NWSAdapter(stations=stations)
