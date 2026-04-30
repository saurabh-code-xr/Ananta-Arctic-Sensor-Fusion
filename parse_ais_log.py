"""
AIS Log Parser
Reads a US Coast Guard / MarineCadastre AIS CSV file and converts it
into our standard sensor fusion input format.

AIS input columns expected (MarineCadastre.gov format):
    MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading, VesselName, VesselType,
    Status, Length, Width, Draft, Cargo, TransceiverClass

Output CSV columns (standard fusion format):
    timestamp, sensor_id, detected, quality, latency_ms

Usage:
    python parse_ais_log.py --csv data/AIS_2024_Zone10.csv
    python parse_ais_log.py --csv data/AIS_2024_Zone10.csv --out data/ais_parsed.csv
"""

import csv
import os
import argparse
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(_HERE, "ais_parsed.csv")

# AIS navigational status codes — 0 = underway using engine (best quality)
# Others indicate anchored, moored, not under command, etc.
_UNDERWAY_STATUSES = {0, 8}   # 0=underway engine, 8=underway sailing

# Bounds check — reject obviously corrupt position fixes
LAT_VALID = (-90.0, 90.0)
LON_VALID = (-180.0, 180.0)
SOG_MAX   = 102.2   # knots — AIS spec max valid value (102.3 = not available)
COG_MAX   = 359.9   # degrees
HDG_MAX   = 359.0   # degrees (511 = not available in AIS spec)


def _parse_dt(raw: str) -> datetime | None:
    """Parse AIS BaseDateTime string. Returns None on failure."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def _derive_quality(row: dict) -> float:
    """
    Derive a [0, 1] quality score from AIS fields.

    Scoring logic (each component contributes equally, then averaged):
      - Position validity:  LAT/LON within bounds          → 0.0 or 1.0
      - SOG validity:       0 <= SOG <= 102.2              → 0.0 or 1.0
      - Heading validity:   0 <= Heading <= 359            → 0.0 or 1.0
      - Status quality:     underway (0 or 8) = good       → 1.0 / 0.6 / 0.3

    Marine operations note: a vessel at anchor (Status=1) is still transmitting
    valid data — we degrade quality slightly but do not zero it, because the
    sensor is working correctly even if the vessel isn't moving.
    """
    scores = []

    # Position validity
    try:
        lat = float(row.get("LAT", 0))
        lon = float(row.get("LON", 0))
        scores.append(1.0 if LAT_VALID[0] <= lat <= LAT_VALID[1]
                              and LON_VALID[0] <= lon <= LON_VALID[1] else 0.0)
    except (ValueError, TypeError):
        scores.append(0.0)

    # SOG validity
    try:
        sog = float(row.get("SOG", 0))
        scores.append(1.0 if 0.0 <= sog <= SOG_MAX else 0.0)
    except (ValueError, TypeError):
        scores.append(0.0)

    # Heading validity (511 = not available in AIS)
    try:
        hdg = float(row.get("Heading", 511))
        scores.append(1.0 if 0.0 <= hdg <= HDG_MAX else 0.5)
    except (ValueError, TypeError):
        scores.append(0.5)   # missing heading is common, not a hard failure

    # Navigational status
    try:
        status = int(float(row.get("Status", 15)))
        if status in _UNDERWAY_STATUSES:
            scores.append(1.0)
        elif status in {1, 2, 3, 5}:   # anchored, moored, restricted
            scores.append(0.6)
        else:                            # 15 = not defined / unknown
            scores.append(0.3)
    except (ValueError, TypeError):
        scores.append(0.3)

    return round(sum(scores) / len(scores), 3)


def _derive_latency(dt_current: datetime, dt_previous: datetime | None) -> float:
    """
    Derive latency_ms from time gap between consecutive records for same vessel.

    AIS transponders nominally transmit every 2–10 seconds (Class A underway).
    Gaps > 60s suggest poor reception, relay delay, or intermittent transmission.
    We express the gap in milliseconds to match our fusion engine input format.
    """
    if dt_previous is None:
        return 100.0   # first record for this vessel — assume nominal
    delta_ms = abs((dt_current - dt_previous).total_seconds()) * 1000.0
    return round(delta_ms, 1)


def _sensor_id(row: dict) -> str:
    """Return a human-readable sensor ID: VesselName if available, else MMSI."""
    name = row.get("VesselName", "").strip()
    mmsi = row.get("MMSI", "").strip()
    if name and name.upper() not in ("", "UNKNOWN", "N/A"):
        return f"{name}_{mmsi}" if mmsi else name
    return mmsi if mmsi else "UNKNOWN"


def _detected(row: dict, quality: float) -> bool:
    """
    A vessel is 'detected' (actively transmitting valid position) if:
      - quality > 0.4 (position + SOG checks pass)
      - LAT/LON are non-zero (0,0 is the AIS null island — invalid fix)
    """
    try:
        lat = float(row.get("LAT", 0))
        lon = float(row.get("LON", 0))
        if lat == 0.0 and lon == 0.0:
            return False
    except (ValueError, TypeError):
        return False
    return quality > 0.4


def parse_ais_log(input_csv: str, output_csv: str) -> int:
    """
    Parse an AIS CSV file into the standard fusion sensor format.

    Returns the number of records written.
    """
    last_dt: dict[str, datetime] = {}   # sensor_id → last seen datetime
    records = []

    with open(input_csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = _parse_dt(row.get("BaseDateTime", ""))
            if dt is None:
                continue   # skip rows with unparseable timestamps

            sensor_id = _sensor_id(row)
            quality   = _derive_quality(row)
            latency   = _derive_latency(dt, last_dt.get(sensor_id))
            detected  = _detected(row, quality)

            records.append({
                "timestamp":  dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "sensor_id":  sensor_id,
                "detected":   detected,
                "quality":    quality,
                "latency_ms": latency,
            })

            last_dt[sensor_id] = dt

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp", "sensor_id", "detected", "quality", "latency_ms"]
        )
        writer.writeheader()
        writer.writerows(records)

    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse AIS log → fusion sensor CSV")
    parser.add_argument("--csv",  required=True, help="Path to raw AIS CSV file")
    parser.add_argument("--out",  default=DEFAULT_OUT,
                        help=f"Output path (default: {DEFAULT_OUT})")
    args = parser.parse_args()

    input_path  = args.csv
    output_path = args.out

    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"AIS input file not found: {input_path}")

    print(f"Parsing: {input_path}")
    n = parse_ais_log(input_path, output_path)
    print(f"Extracted {n} records -> {output_path}")


if __name__ == "__main__":
    main()
