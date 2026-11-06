"""
Generic field-log -> fusion-engine sensor adapter.

NORCAT (or any other facility) will export sensor data in whatever format
their own logging stack produces -- not necessarily matching the simulated
schema in analyze_norcat_testbed.py. This module provides a configurable,
column-mapping-driven CSV loader so a real log can be wired into the real
fusion/confidence engine (data_fusion.fusion_engine.fuse_sensors etc.)
without writing a one-off parser on site, in a tunnel, with no signal.

Two input shapes are supported:
  - "long":  one row per sensor reading (a time col, a sensor-name col,
             plus quality/latency/detected columns)
  - "wide":  one row per timestep, with separate columns per sensor
             (e.g. ins_quality, lidar_quality, ins_latency_ms, ...)

Most real sensor stacks report diagnostics that aren't already a 0..1
"quality" score (covariance, match score, residual, SNR, feature count).
QualityMap performs an explicit, auditable linear rescale from a raw
metric onto the engine's expected 0..1 scale -- this mapping choice
should always be stated alongside any result derived from it, since it
is an engineering judgment call, not a measurement.

Example (long format, a single "match_score" column rescaled to quality):
    schema = LogSchema(
        format="long",
        time_col="timestamp_s",
        sensor_col="sensor_name",
        quality_col="match_score",
        quality_map=QualityMap(good_value=0.95, bad_value=0.30),
        latency_col="processing_ms",
        detected_col="valid",
    )
    steps = load_field_log("norcat_run1.csv", schema)
    # steps is now [[{"sensor","detected","quality","latency"}, ...], ...]
    # exactly the input shape fuse_sensors() expects, one entry per timestep.

Example (wide format, one row per timestep):
    schema = LogSchema(
        format="wide",
        time_col="t_s",
        sensor_columns={
            "INS":   {"quality": "ins_q", "latency": "ins_latency_ms"},
            "LIDAR": {"quality": "lidar_q", "latency": "lidar_latency_ms", "detected": "lidar_valid"},
        },
    )
    steps = load_field_log("norcat_run1.csv", schema)
"""

import csv
from dataclasses import dataclass


@dataclass
class QualityMap:
    """Rescales an arbitrary raw diagnostic metric onto the engine's 0..1
    quality scale: quality = clamp((raw - bad_value) / (good_value - bad_value), 0, 1).
    Set invert=True when a LOWER raw value means BETTER quality (e.g. a
    covariance or residual metric, where small = good)."""
    good_value: float
    bad_value: float
    invert: bool = False

    def apply(self, raw) -> float:
        if raw is None or raw == "":
            return 0.5  # unknown -- neutral default, never silently claim high confidence
        raw = float(raw)
        lo, hi = (self.bad_value, self.good_value)
        if self.invert:
            raw, lo, hi = -raw, -lo, -hi
        if hi == lo:
            return 1.0
        q = (raw - lo) / (hi - lo)
        return max(0.0, min(1.0, q))


@dataclass
class LogSchema:
    format: str                       # "long" or "wide"
    time_col: str
    detected_col: str | None = None
    latency_col: str | None = None
    quality_col: str | None = None
    sensor_col: str | None = None             # required for "long"
    sensor_columns: dict | None = None        # required for "wide": {name: {"quality":col,"latency":col,"detected":col}}
    quality_map: QualityMap | None = None     # optional raw->0..1 rescale; if omitted, raw value is clamped to 0..1 as-is
    default_latency_ms: float = 50.0
    default_detected: bool = True


def _to_quality(raw, qmap: QualityMap | None) -> float:
    if raw in (None, ""):
        return 0.5
    if qmap is not None:
        return qmap.apply(raw)
    return max(0.0, min(1.0, float(raw)))


def _to_bool(raw, default: bool) -> bool:
    if raw in (None, ""):
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "detected", "valid")


def load_field_log(csv_path: str, schema: LogSchema) -> list:
    """Load a field-log CSV into the engine's per-timestep sensor-list
    format: [[{"sensor","detected","quality","latency"}, ...], ...]."""
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if schema.format == "long":
        if not schema.sensor_col:
            raise ValueError("LogSchema.sensor_col is required for format='long'")
        by_time = {}
        for row in rows:
            t = row[schema.time_col]
            quality = _to_quality(row.get(schema.quality_col) if schema.quality_col else None, schema.quality_map)
            latency_raw = row.get(schema.latency_col) if schema.latency_col else None
            latency = float(latency_raw) if latency_raw else schema.default_latency_ms
            detected = _to_bool(row.get(schema.detected_col) if schema.detected_col else None, schema.default_detected)
            by_time.setdefault(t, []).append({
                "sensor": row[schema.sensor_col],
                "detected": detected,
                "quality": round(quality, 3),
                "latency": round(latency, 1),
            })
        ordered_keys = sorted(by_time.keys(), key=lambda v: float(v))
        return [by_time[k] for k in ordered_keys]

    elif schema.format == "wide":
        if not schema.sensor_columns:
            raise ValueError("LogSchema.sensor_columns is required for format='wide'")
        steps = []
        for row in rows:
            sensors = []
            for sensor_name, cols in schema.sensor_columns.items():
                q_raw = row.get(cols.get("quality")) if cols.get("quality") else None
                quality = _to_quality(q_raw, schema.quality_map)
                latency_raw = row.get(cols.get("latency")) if cols.get("latency") else None
                latency = float(latency_raw) if latency_raw else schema.default_latency_ms
                detected = _to_bool(row.get(cols.get("detected")) if cols.get("detected") else None, schema.default_detected)
                sensors.append({
                    "sensor": sensor_name,
                    "detected": detected,
                    "quality": round(quality, 3),
                    "latency": round(latency, 1),
                })
            steps.append(sensors)
        return steps

    else:
        raise ValueError(f"Unknown LogSchema.format: {schema.format!r} (expected 'long' or 'wide')")
