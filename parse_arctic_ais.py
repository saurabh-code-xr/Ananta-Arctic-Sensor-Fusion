"""
Arctic AIS Log Parser
Reads an AIS CSV file (MarineCadastre / PAME / Transport Canada format),
filters for Arctic coordinates (lat > 60N), and converts to the standard
Ananta Meridian fusion sensor input format.

Arctic-specific design decisions
---------------------------------
1. Satellite AIS gap awareness
   In the Arctic, land-based AIS receivers are absent. Data comes exclusively
   from satellite passes (OrbComm, Iridium, Spire). Coverage windows are
   10-25 minutes apart. A latency_ms of 600,000-1,500,000 is NORMAL, not
   degraded. This parser does NOT penalise normal satellite gaps.

2. Quality scoring reflects Arctic reality
   - Heading=511 (AIS "not available") is common between satellite passes
     and during ice manoeuvring — scored as partial, not failure
   - SOG=0 near an anchoring status is expected — scored accordingly
   - Status=1 (anchored) is operationally valid in Arctic ops

3. Degradation signals that DO matter
   - Position fix at 0,0 (null island) = bad fix
   - Latency > 4 hours = genuine loss of contact (not satellite gap)
   - Quality score < 0.3 = sensor considered not detected

References:
   PAME Arctic Shipping Status Report 2024
   ASTD Data Document September 2023 (pame.is)
   OrbComm satellite AIS gap analysis (euro-sd.com/2024/05)

Usage:
    python parse_arctic_ais.py --csv data/arctic_ais_sample.csv
    python parse_arctic_ais.py --csv data/arctic_ais_sample.csv --out data/arctic_parsed.csv
    python parse_arctic_ais.py --csv data/arctic_ais_sample.csv --lat-min 65.0
"""

import csv
import os
import argparse
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(_HERE, "data", "arctic_ais_parsed.csv")

# Arctic filter — default 60N, Canadian Arctic EEZ
DEFAULT_LAT_MIN = 60.0

# AIS navigational status codes
_UNDERWAY = {0, 8}          # underway engine / sailing
_RESTRICTED = {1, 2, 3, 5}  # anchored, moored, constrained by draught

# AIS spec limits
SOG_MAX = 102.2
HDG_UNAVAILABLE = 511

# Genuine loss of contact threshold (satellite gaps are up to ~25 min = 1500s)
# Beyond 4 hours = genuine degradation in Arctic context
GENUINE_LOSS_THRESHOLD_MS = 4 * 60 * 60 * 1000   # 4 hours in ms


def _parse_dt(raw: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def _derive_quality(row: dict) -> float:
    """
    Derive quality score [0, 1] from AIS fields with Arctic-aware logic.

    Component weights (each 0.25):
      1. Position validity — lat/lon within bounds and not null island
      2. SOG validity — within AIS spec range
      3. Heading validity — 511 = partial credit (common in Arctic, not a failure)
      4. Nav status — underway = full, restricted = partial, unknown = low
    """
    scores = []

    # 1. Position validity
    try:
        lat = float(row.get("LAT", 0))
        lon = float(row.get("LON", 0))
        if lat == 0.0 and lon == 0.0:
            scores.append(0.0)   # null island — bad fix
        elif -90 <= lat <= 90 and -180 <= lon <= 180:
            scores.append(1.0)
        else:
            scores.append(0.0)
    except (ValueError, TypeError):
        scores.append(0.0)

    # 2. SOG validity
    try:
        sog = float(row.get("SOG", 0))
        scores.append(1.0 if 0.0 <= sog <= SOG_MAX else 0.0)
    except (ValueError, TypeError):
        scores.append(0.0)

    # 3. Heading validity — 511 is "not available" per AIS spec
    #    In Arctic ops, satellite AIS often delivers heading=511 between passes.
    #    This is NOT a sensor failure — give partial credit.
    try:
        hdg = int(float(row.get("Heading", HDG_UNAVAILABLE)))
        if 0 <= hdg <= 359:
            scores.append(1.0)
        elif hdg == HDG_UNAVAILABLE:
            scores.append(0.5)   # partial — common in Arctic, not a failure
        else:
            scores.append(0.0)
    except (ValueError, TypeError):
        scores.append(0.5)

    # 4. Nav status
    try:
        status = int(float(row.get("Status", 15)))
        if status in _UNDERWAY:
            scores.append(1.0)
        elif status in _RESTRICTED:
            scores.append(0.6)   # valid Arctic operation (anchoring in ice)
        else:
            scores.append(0.2)   # unknown status
    except (ValueError, TypeError):
        scores.append(0.2)

    return round(sum(scores) / len(scores), 3)


def _derive_latency(dt_current: datetime, dt_previous: datetime | None) -> float:
    """
    Latency = time gap between consecutive records for the same vessel, in ms.

    Arctic note: gaps of 600,000-1,500,000ms (10-25 min) are normal satellite
    pass intervals and do NOT indicate degradation. The fusion engine's marine
    tau_ms=500 config handles this correctly — high latency reduces trust weight
    smoothly rather than snapping to LOW.
    """
    if dt_previous is None:
        return 500.0   # first record — assume mid-pass nominal
    delta_ms = abs((dt_current - dt_previous).total_seconds()) * 1000.0
    return round(delta_ms, 1)


def _sensor_id(row: dict) -> str:
    name = row.get("VesselName", "").strip()
    mmsi = row.get("MMSI", "").strip()
    if name and name.upper() not in ("", "UNKNOWN", "N/A", "@@@@@"):
        return f"{name}_{mmsi}" if mmsi else name
    return mmsi if mmsi else "UNKNOWN"


def _detected(row: dict, quality: float, latency_ms: float) -> bool:
    """
    Vessel is detected (valid position fix) if:
    - quality > 0.3 (position and SOG checks pass)
    - not null island (0,0)
    - latency < genuine loss threshold (4 hours)
    """
    if quality <= 0.3:
        return False
    if latency_ms > GENUINE_LOSS_THRESHOLD_MS:
        return False
    try:
        lat = float(row.get("LAT", 0))
        lon = float(row.get("LON", 0))
        return not (lat == 0.0 and lon == 0.0)
    except (ValueError, TypeError):
        return False


def parse_arctic_ais(input_csv: str, output_csv: str, lat_min: float = DEFAULT_LAT_MIN) -> tuple[int, int]:
    """
    Parse AIS CSV, filter for Arctic (lat >= lat_min), output standard sensor CSV.

    Returns (records_read, records_written).
    """
    last_dt: dict[str, datetime] = {}
    records_out = []
    records_read = 0

    with open(input_csv, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records_read += 1

            # Filter: Arctic coordinates only
            try:
                lat = float(row.get("LAT", 0))
            except (ValueError, TypeError):
                continue
            if lat < lat_min:
                continue

            dt = _parse_dt(row.get("BaseDateTime", ""))
            if dt is None:
                continue

            sensor_id = _sensor_id(row)
            quality   = _derive_quality(row)
            latency   = _derive_latency(dt, last_dt.get(sensor_id))
            detected  = _detected(row, quality, latency)

            records_out.append({
                "timestamp":  dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "sensor_id":  sensor_id,
                "detected":   detected,
                "quality":    quality,
                "latency_ms": latency,
            })

            last_dt[sensor_id] = dt

    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp", "sensor_id", "detected", "quality", "latency_ms"]
        )
        writer.writeheader()
        writer.writerows(records_out)

    return records_read, len(records_out)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse Arctic AIS log -> standard fusion sensor CSV"
    )
    parser.add_argument("--csv",     required=True, help="Path to raw AIS CSV")
    parser.add_argument("--out",     default=DEFAULT_OUT, help="Output path")
    parser.add_argument("--lat-min", type=float, default=DEFAULT_LAT_MIN,
                        help=f"Minimum latitude filter (default: {DEFAULT_LAT_MIN}N)")
    args = parser.parse_args()

    if not os.path.isfile(args.csv):
        raise FileNotFoundError(f"Input file not found: {args.csv}")

    print(f"Parsing: {args.csv}")
    print(f"Arctic filter: lat >= {args.lat_min}N")
    total, written = parse_arctic_ais(args.csv, args.out, args.lat_min)
    print(f"Read {total} records | Arctic records written: {written} -> {args.out}")


if __name__ == "__main__":
    main()
