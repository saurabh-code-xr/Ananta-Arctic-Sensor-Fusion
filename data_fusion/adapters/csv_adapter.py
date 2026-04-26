"""
CSV sensor adapter.

Reads pre-recorded sensor logs from a CSV file.
Useful for testing with real hardware logs before live integration.

Expected CSV format:
    timestamp,sensor_id,detected,quality,latency_ms
    2024-01-01T00:00:00,A,True,0.85,120
    2024-01-01T00:00:00,B,False,0.42,380
    ...

Rows with the same timestamp are grouped into one time step.
"""

import csv
from data_fusion.adapters.base import SensorAdapter
from data_fusion.logger import get_logger

logger = get_logger("adapter.csv")


class CSVAdapter(SensorAdapter):
    """Load sensor readings from a CSV file."""

    def __init__(
        self,
        file_path: str,
        sensor_col: str = "sensor_id",
        detected_col: str = "detected",
        quality_col: str = "quality",
        latency_col: str = "latency_ms",
        timestamp_col: str = "timestamp",
    ):
        self.file_path = file_path
        self.sensor_col = sensor_col
        self.detected_col = detected_col
        self.quality_col = quality_col
        self.latency_col = latency_col
        self.timestamp_col = timestamp_col

    def fetch(self) -> list[list[dict]]:
        """
        Read CSV and group rows by timestamp into time steps.
        Returns list of time steps, each a list of sensor reading dicts.
        """
        try:
            with open(self.file_path, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except FileNotFoundError:
            logger.error("CSV file not found: %s", self.file_path)
            return []
        except Exception as e:
            logger.error("Failed to read CSV '%s': %s", self.file_path, e)
            return []

        if not rows:
            logger.warning("CSV file '%s' is empty.", self.file_path)
            return []

        # Group by timestamp into time steps
        steps_by_ts: dict[str, list[dict]] = {}
        for row in rows:
            ts = row.get(self.timestamp_col, "unknown")
            reading = self._parse_row(row)
            if reading:
                steps_by_ts.setdefault(ts, []).append(reading)

        steps = list(steps_by_ts.values())
        logger.info("CSV adapter loaded %d time steps from '%s'", len(steps), self.file_path)
        return steps

    def _parse_row(self, row: dict) -> dict | None:
        try:
            return {
                "sensor": str(row[self.sensor_col]).strip(),
                "detected": str(row[self.detected_col]).strip().lower() in ("true", "1", "yes"),
                "quality": float(row[self.quality_col]),
                "latency": float(row[self.latency_col]),
            }
        except (KeyError, ValueError) as e:
            logger.warning("Skipping malformed CSV row %s: %s", row, e)
            return None
