"""
Arctic AIS -> Ananta Meridian Fusion Engine Analysis
Runs parsed Canadian Arctic AIS vessel data through the full fusion pipeline.

This demonstrates the engine's ability to distinguish:
  - Normal satellite AIS gaps (10-25 min, operationally expected)
  - Genuine sensor degradation (loss of fix, null island, > 4hr gap)
  - Vessel disagreement patterns (proxy for spoofing or EW interference)

Usage:
    python analyze_arctic_ais.py --csv data/arctic_ais_parsed.csv
    python analyze_arctic_ais.py --csv data/arctic_ais_parsed.csv --step 6
"""

import csv
import sys
import os
import json
import argparse
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from data_fusion.fusion_engine import fuse_sensors
from data_fusion.confidence_engine import compute_confidence
from data_fusion.reliability_memory import update_reliability_history
from data_fusion import config as cfg_module

DEFAULT_STEP_SIZE = 6   # 6 vessels per time step (matches our 6-vessel dataset)
DEFAULT_CONFIG    = os.path.join(_HERE, "config_arctic_ais.yaml")
RESULTS_DIR       = os.path.join(_HERE, "results")


def load_parsed_ais(csv_path: str) -> list[dict]:
    records = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append({
                "timestamp":  row["timestamp"],
                "sensor_id":  row["sensor_id"],
                "detected":   row["detected"].strip().lower() == "true",
                "quality":    float(row["quality"]),
                "latency_ms": float(row["latency_ms"]),
            })
    return records


def records_to_steps(records: list[dict], step_size: int) -> list[list[dict]]:
    """Group records into time steps. Each record = one sensor input."""
    steps = []
    for i in range(0, len(records), step_size):
        chunk = records[i:i + step_size]
        sensors = [
            {
                "sensor":   rec["sensor_id"],
                "detected": rec["detected"],
                "quality":  rec["quality"],
                "latency":  rec["latency_ms"],
            }
            for rec in chunk
        ]
        if sensors:
            steps.append(sensors)
    return steps


def save_results(payload: dict, results_dir: str) -> str:
    os.makedirs(results_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(results_dir, f"arctic_ais_analysis_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out_path


def run_analysis(csv_path: str, step_size: int, config_path: str | None = None) -> dict:
    print("=" * 68)
    print("ANANTA MERIDIAN -- Canadian Arctic AIS Vessel Fusion Analysis")
    print("=" * 68)
    print("Dataset: Calibrated synthetic Arctic AIS (6 vessels, 2024-08-15)")
    print("Grounded in: PAME ASTD 2023, Arctic Council Shipping Report 2024")
    print("=" * 68)

    config = cfg_module.load(config_path)
    records = load_parsed_ais(csv_path)

    if not records:
        print("ERROR: No records loaded.")
        sys.exit(1)

    steps = records_to_steps(records, step_size)

    print(f"\nAIS records loaded  : {len(records)}")
    print(f"Time steps created  : {len(steps)} (step size = {step_size})")
    print(f"\n{'Step':<6} {'Sensors':<9} {'Avg Quality':<14} {'Avg Latency(ms)':<18}"
          f"{'Fused':<8} {'Confidence':<12} {'Reasons'}")
    print("-" * 100)

    reliability_history: dict = {}
    step_results = []
    confidence_history = []

    for step_num, sensors in enumerate(steps):
        fusion     = fuse_sensors(sensors, reliability_history=reliability_history, config=config)
        confidence = compute_confidence(fusion, sensors, config=config)
        reliability_history = update_reliability_history(reliability_history, sensors)

        level   = confidence["level"]
        reasons = "; ".join(confidence["reasons"][:2]) if confidence["reasons"] else "OK"
        avg_q   = sum(s["quality"] for s in sensors) / len(sensors)
        avg_l   = sum(s["latency"] for s in sensors) / len(sensors)
        fused   = "YES" if fusion["fused_detection"] else "NO"

        confidence_history.append(level)

        print(f"{step_num + 1:<6} {len(sensors):<9} {avg_q:<14.3f} {avg_l:<18.0f}"
              f"{fused:<8} {level:<12} {reasons}")

        step_results.append({
            "step":             step_num + 1,
            "sensor_count":     len(sensors),
            "avg_quality":      round(avg_q, 3),
            "avg_latency_ms":   round(avg_l, 1),
            "fused_detection":  fusion["fused_detection"],
            "confidence_level": level,
            "reasons":          confidence["reasons"],
            "actions":          confidence.get("actions", []),
        })

    # Summary
    total  = len(confidence_history)
    high   = confidence_history.count("HIGH")
    medium = confidence_history.count("MEDIUM")
    low    = confidence_history.count("LOW")

    print("\n" + "=" * 68)
    print("ARCTIC FUSION CONFIDENCE SUMMARY")
    print("=" * 68)
    print(f"Total time steps    : {total}")
    print(f"HIGH confidence     : {high}  ({high / total * 100:.0f}%)")
    print(f"MEDIUM confidence   : {medium}  ({medium / total * 100:.0f}%)")
    print(f"LOW confidence      : {low}  ({low / total * 100:.0f}%)")
    print(f"Degradation detected: {'YES' if low > 0 or medium > 0 else 'NO'}")

    results_payload = {
        "source":          csv_path,
        "dataset":         "Calibrated synthetic Arctic AIS — 6 Canadian Arctic vessels",
        "date_range":      "2024-08-15",
        "step_size":       step_size,
        "total_records":   len(records),
        "total_steps":     total,
        "summary":         {"high": high, "medium": medium, "low": low},
        "steps":           step_results,
    }

    out_path = save_results(results_payload, RESULTS_DIR)
    print(f"\nResults saved -> {out_path}")

    return results_payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Arctic AIS data through Ananta Meridian fusion engine"
    )
    parser.add_argument("--csv",  required=True,
                        help="Parsed Arctic AIS CSV (from parse_arctic_ais.py)")
    parser.add_argument("--step",   type=int, default=DEFAULT_STEP_SIZE,
                        help=f"Records per time step (default: {DEFAULT_STEP_SIZE})")
    parser.add_argument("--config", default=DEFAULT_CONFIG,
                        help=f"Config YAML path (default: config_arctic_ais.yaml)")
    args = parser.parse_args()

    if not os.path.isfile(args.csv):
        raise FileNotFoundError(f"CSV not found: {args.csv}")

    run_analysis(args.csv, args.step, config_path=args.config)


if __name__ == "__main__":
    main()
