"""
DJI Binary Log Parser
Scans fc_log.log for LGY markers and extracts telemetry into flight_data.csv.
Output CSV is saved alongside this script for permanence.
"""

import struct
import csv
import os

_HERE    = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(_HERE, "..", "Evidence Logs", "fc_log.log")
OUT_CSV  = os.path.join(_HERE, "flight_data.csv")

MARKER = b"LGY"


def parse_dji_log(file_path: str, output_csv: str) -> int:
    with open(file_path, "rb") as f:
        data = f.read()

    records = []
    pos = 0
    record_id = 0

    while pos < len(data) - 30:
        idx = data.find(MARKER, pos)
        if idx == -1:
            break

        chunk = data[idx + 3: idx + 30]
        if len(chunk) < 14:
            pos = idx + 1
            continue

        try:
            values = struct.unpack_from("<BBHBBHBBBB", chunk[:14])
        except struct.error:
            pos = idx + 1
            continue

        raw_signal   = values[0]
        raw_quality  = values[1]
        raw_latency  = values[2]
        raw_battery  = values[3]

        signal_strength = round((raw_signal / 255.0) * 100, 1)
        quality         = round(raw_quality / 255.0, 3)
        latency_ms      = round(100 + (raw_latency % 500), 1)
        battery_pct     = round((raw_battery / 255.0) * 100, 1)
        detected        = quality > 0.4 and signal_strength > 40.0

        records.append({
            "record_id":       record_id,
            "signal_strength": signal_strength,
            "quality":         quality,
            "latency_ms":      latency_ms,
            "battery_pct":     battery_pct,
            "detected":        detected,
        })

        record_id += 1
        pos = idx + 3

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "record_id", "signal_strength", "quality",
            "latency_ms", "battery_pct", "detected"
        ])
        writer.writeheader()
        writer.writerows(records)

    return len(records)


if __name__ == "__main__":
    print(f"Parsing: {LOG_PATH}")
    n = parse_dji_log(LOG_PATH, OUT_CSV)
    print(f"Extracted {n} records -> {OUT_CSV}")
