"""
AIS Log → Fusion Engine Analysis
Runs parsed AIS vessel data through the Ananta Meridian fusion engine.
Demonstrates confidence-aware fusion under real marine sensing conditions.

Usage:
    python analyze_ais.py --csv data/ais_parsed.csv
    python analyze_ais.py --csv data/ais_parsed.csv --step 10
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

DEFAULT_STEP_SIZE = 5
RESULTS_DIR = os.path.join(_HERE, "results")


def load_ais_data(csv_path: str) -> list[dict]:
    """Load parsed AIS CSV into list of record dicts."""
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
    """
    Group records into time steps for fusion.
    Each record becomes one sensor input; every step_size records = one time step.
    Sensor field uses sensor_id; latency field uses latency_ms (fusion engine key).
    """
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


def save_results(results: dict, results_dir: str) -> str:
    """Save analysis results to a timestamped JSON file."""
    os.makedirs(results_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(results_dir, f"ais_analysis_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return out_path


def run_analysis(csv_path: str, step_size: int) -> None:
    print("=" * 65)
    print("ANANTA MERIDIAN — AIS Marine Vessel Fusion Analysis")
    print("=" * 65)

    config = cfg_module.load(None)
    records = load_ais_data(csv_path)

    if not records:
        print("ERROR: No records loaded. Check CSV path and format.")
        sys.exit(1)

    steps = records_to_steps(records, step_size)

    print(f"\nAIS records loaded : {len(records)}")
    print(f"Time steps created : {len(steps)} (step size = {step_size})")
    print(f"\n{'Step':<6} {'Sensors':<9} {'Avg Quality':<14} {'Avg Latency':14} "
          f"{'Fused':<8} {'Confidence':<12} {'Reasons'}")
    print("-" * 95)

    reliability_history: dict = {}
    step_results = []

    for step_num, sensors in enumerate(steps):
        fusion     = fuse_sensors(sensors, reliability_history=reliability_history)
        confidence = compute_confidence(fusion, sensors)
        reliability_history = update_reliability_history(reliability_history, sensors)

        level   = confidence["level"]
        reasons = "; ".join(confidence["reasons"][:2]) if confidence["reasons"] else "OK"
        avg_q   = sum(s["quality"] for s in sensors) / len(sensors)
        avg_l   = sum(s["latency"] for s in sensors) / len(sensors)
        fused   = "YES" if fusion["fused_detection"] else "NO"

        print(f"{step_num + 1:<6} {len(sensors):<9} {avg_q:<14.3f} {avg_l:<14.1f} "
              f"{fused:<8} {level:<12} {reasons}")

        step_results.append({
            "step":              step_num + 1,
            "sensor_count":      len(sensors),
            "avg_quality":       round(avg_q, 3),
            "avg_latency_ms":    round(avg_l, 1),
            "fused_detection":   fusion["fused_detection"],
            "confidence_level":  level,
            "reasons":           confidence["reasons"],
            "actions":           confidence.get("actions", []),
        })

    # Summary
    levels   = [r["confidence_level"] for r in step_results]
    total    = len(levels)
    high     = levels.count("HIGH")
    medium   = levels.count("MEDIUM")
    low      = levels.count("LOW")

    print("\n" + "=" * 65)
    print("MARINE FUSION CONFIDENCE SUMMARY")
    print("=" * 65)
    print(f"Total time steps  : {total}")
    print(f"HIGH confidence   : {high}  ({high / total * 100:.0f}%)")
    print(f"MEDIUM confidence : {medium}  ({medium / total * 100:.0f}%)")
    print(f"LOW confidence    : {low}  ({low / total * 100:.0f}%)")
    print(f"Degradation detected: {'YES' if low > 0 or medium > 0 else 'NO'}")

    # Save results
    results_payload = {
        "source":       csv_path,
        "step_size":    step_size,
        "total_records": len(records),
        "total_steps":  total,
        "summary": {
            "high":   high,
            "medium": medium,
            "low":    low,
        },
        "steps": step_results,
    }
    out_path = save_results(results_payload, RESULTS_DIR)
    print(f"\nResults saved -> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run AIS marine vessel data through the Ananta Meridian fusion engine"
    )
    parser.add_argument(
        "--csv", required=True,
        help="Path to parsed AIS CSV (output of parse_ais_log.py)"
    )
    parser.add_argument(
        "--step", type=int, default=DEFAULT_STEP_SIZE,
        help=f"Records per time step (default: {DEFAULT_STEP_SIZE})"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.csv):
        raise FileNotFoundError(f"CSV not found: {args.csv}")

    run_analysis(args.csv, args.step)


if __name__ == "__main__":
    main()
