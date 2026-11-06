"""
NORCAT Underground GNSS-Denied Testbed -> Ananta Meridian Fusion Engine
========================================================================

Runs a simulated underground GNSS-denied navigation scenario (classical
INS + LiDAR odometry baseline, plus a quantum-magnetometer-style anomaly
sweep) through the REAL Ananta Meridian fusion/confidence/reliability
engine -- the same data_fusion.fuse_sensors / compute_confidence /
update_reliability_history calls used by analyze_dji_flight.py,
analyze_marine_vessel.py and analyze_arctic_ais.py.

STATUS -- READ BEFORE PRESENTING THIS ANYWHERE
------------------------------------------------
Every sensor reading in this script is SIMULATED. The INS drift model
(t^1.5 growth), the LiDAR-aided residual drift, the "degraded corridor"
zones, and the magnetometer SNR/anomaly model are REASONABLE ENGINEERING
ASSUMPTIONS, not measured constants from NORCAT or from Ananta Meridian's
own hardware. They exist to exercise the real fusion engine end-to-end on
an underground-GNSS-denied-shaped problem before any real facility data
exists.

What IS real: the fusion/confidence/reliability code path itself
(data_fusion.fusion_engine, confidence_engine, reliability_memory --
unmodified, same modules validated on the DJI Mini 2 flight log and the
Arctic AIS data). What is NOT real: the sensor values being fed into it.

Do not present the specific numbers below (drift rates, SNR values, the
exact minute-mark of degradation) to NORCAT, IDEaS, or any customer as
measured results. The only defensible claim from this script is the
PATTERN: a confidence-aware fusion layer can surface sensor disagreement
and quality degradation measurably earlier than a raw-position-error
threshold would, in a scenario shaped like an underground GNSS-denied
corridor.

REAL-DATA PATH (once NORCAT facility logs exist): this script is now
paired with two modules that make that swap a config change, not a
rewrite:
  - parse_field_log.py      -- generic column-mapping CSV adapter for
                                whatever log format the facility exports,
                                producing the same sensor-list shape this
                                script generates in generate_timestep_sensors().
  - ground_truth_compare.py -- computes REAL position error against an
                                independent survey/ground-truth track and
                                runs the same early_warning_summary() this
                                script uses, so the metric definition is
                                identical between this simulated run and
                                a future real one.
  - generate_field_report.py -- turns either run's JSON output into a
                                one-page markdown+chart report.

Usage:
    python analyze_norcat_testbed.py
    FUSION_CONFIG=config_norcat.yaml python analyze_norcat_testbed.py
"""

import csv
import json
import math
import os
import random
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from data_fusion.fusion_engine import fuse_sensors
from data_fusion.confidence_engine import compute_confidence
from data_fusion.reliability_memory import update_reliability_history
from data_fusion import config as cfg_module
from ground_truth_compare import early_warning_summary

DEFAULT_CONFIG_PATH = os.path.join(_HERE, "config_norcat.yaml")

DURATION_S = 1800     # 30-minute simulated underground traverse
DT_S = 5.0            # one fused estimate every 5 seconds -> 361 time steps

# INS drift model constants (simulated -- see module docstring)
K_INS = 0.015         # unaided strapdown INS error growth coefficient
K_LIDAR = 0.004        # LiDAR-odometry-aided residual drift coefficient
CORRIDOR_PERIOD_S = 420     # a feature-poor corridor section every 7 minutes
CORRIDOR_DURATION_S = 90    # lasting 90 seconds
CORRIDOR_DRIFT_MULT = 3.0   # LiDAR drift triples when the corridor starves it of features

# Magnetometer model constants (simulated -- see module docstring)
BACKGROUND_FIELD_NT = 50000.0
EQUIPMENT_PERIOD_S = 300     # passing ferrous mining equipment every 5 minutes
EQUIPMENT_DURATION_S = 60
SNR_DETECTABLE_THRESHOLD = 10.0

# Mapping from the physical simulation to sensor "quality" (0..1) consumed by
# the real confidence_engine -- the engine has no concept of "meters of
# drift" or "dB of SNR", so this is the translation layer a real adapter
# would also need to write.
INS_QUALITY_ERROR_CEILING_M = 10.0   # at/above this drift, INS quality bottoms out
LIDAR_QUALITY_FLOOR_CORRIDOR = 0.40
LIDAR_QUALITY_BASELINE = 0.92
QMAG_QUALITY_SNR_CEILING = 25.0


def in_corridor(t_s: float) -> bool:
    return (t_s % CORRIDOR_PERIOD_S) < CORRIDOR_DURATION_S


def near_equipment(t_s: float) -> bool:
    return (t_s % EQUIPMENT_PERIOD_S) < EQUIPMENT_DURATION_S


def generate_timestep_sensors(t_s: float, rng: random.Random, prev_ins_error: float, prev_lidar_error: float):
    """
    Produce one time step's worth of sensor readings in the schema the real
    fusion engine expects: [{"sensor", "detected", "quality", "latency"}, ...]

    A real NORCAT-data adapter would replace this function's BODY with a
    parser over logged INS/LiDAR/magnetometer records; the OUTPUT SHAPE
    (sensor name, detected flag, quality 0..1, latency in ms) would stay
    identical, exactly as analyze_dji_flight.py's records_to_steps() does
    for drone telemetry.
    """
    corridor = in_corridor(t_s)
    equipment = near_equipment(t_s)

    # --- INS: unaided drift grows ~ t^1.5, always produces a reading ---
    ins_error = K_INS * (t_s ** 1.5) / 100.0 + rng.gauss(0, 0.05)
    ins_error = max(0.0, ins_error)
    ins_quality = max(0.15, 1.0 - min(ins_error, INS_QUALITY_ERROR_CEILING_M) / INS_QUALITY_ERROR_CEILING_M)
    ins_latency = 20 + rng.gauss(0, 3)

    # --- LiDAR: aided residual drift, corridor triples the rate ---
    lidar_rate = K_LIDAR * (CORRIDOR_DRIFT_MULT if corridor else 1.0)
    lidar_error = prev_lidar_error + lidar_rate * DT_S + rng.gauss(0, 0.02)
    lidar_error = max(0.0, lidar_error)
    lidar_quality = LIDAR_QUALITY_FLOOR_CORRIDOR if corridor else LIDAR_QUALITY_BASELINE
    lidar_quality = max(0.1, lidar_quality - min(lidar_error, 5.0) / 5.0 * 0.15 + rng.gauss(0, 0.02))
    lidar_quality = min(0.97, max(0.1, lidar_quality))
    lidar_latency = 80 + (40 if corridor else 0) + rng.gauss(0, 5)

    # --- Quantum magnetometer: anomaly SNR against background field ---
    base_signal = 1.0 + rng.gauss(0, 0.1)
    noise_floor = 0.25 if not equipment else 2.5  # ferrous equipment swamps the anomaly signal
    snr = max(0.01, base_signal / noise_floor) * 10.0
    qmag_detected = (snr > SNR_DETECTABLE_THRESHOLD) and not equipment
    qmag_quality = min(0.95, max(0.1, snr / QMAG_QUALITY_SNR_CEILING))
    qmag_latency = 150 + rng.gauss(0, 10)

    sensors = [
        {"sensor": "INS",   "detected": True,          "quality": round(ins_quality, 3),   "latency": round(max(1.0, ins_latency), 1)},
        {"sensor": "LIDAR", "detected": not corridor,  "quality": round(lidar_quality, 3),  "latency": round(max(1.0, lidar_latency), 1)},
        {"sensor": "QMAG",  "detected": qmag_detected,  "quality": round(qmag_quality, 3),  "latency": round(max(1.0, qmag_latency), 1)},
    ]

    physical = {
        "ins_error_m": round(ins_error, 3),
        "lidar_error_m": round(lidar_error, 3),
        "snr": round(snr, 2),
        "corridor": corridor,
        "near_equipment": equipment,
    }

    return sensors, physical, ins_error, lidar_error


def fused_position_error(ins_error_m: float, lidar_error_m: float) -> float:
    """Simple inverse-variance blend of the two physical drift estimates --
    a stand-in for a real EKF/UKF position fusion, used only to report a
    single 'what would the raw navigation error have been' narrative
    number alongside the real confidence engine's output. The confidence
    engine itself never sees this number -- it only sees quality/latency/
    disagreement, exactly as it would for real hardware."""
    w_ins = 1.0 / max(ins_error_m, 0.05) ** 2
    w_lidar = 1.0 / max(lidar_error_m, 0.05) ** 2
    return (ins_error_m * w_ins + lidar_error_m * w_lidar) / (w_ins + w_lidar)


def run(duration_s: float = DURATION_S, dt: float = DT_S, config_path: str = DEFAULT_CONFIG_PATH, out_dir: str = None):
    out_dir = out_dir or _HERE
    config = cfg_module.load(config_path)

    rng = random.Random(42)
    reliability_history = {}

    print("=" * 78)
    print("ANANTA MERIDIAN -- NORCAT Underground GNSS-Denied Testbed (SIMULATED)")
    print("Real fusion_engine / confidence_engine / reliability_memory -- simulated sensors")
    print("=" * 78)
    print(f"Duration: {duration_s:.0f}s ({duration_s/60:.0f} min), step: {dt:.0f}s, config: {os.path.basename(config_path)}")
    print(f"{'t(s)':<7}{'INS_q':<8}{'LIDAR_q':<9}{'QMAG_q':<8}{'Confidence':<12}{'FusedErr(m)':<13}{'Reasons'}")
    print("-" * 100)

    results = []
    t = 0.0
    prev_ins_error = 0.0
    prev_lidar_error = 0.0

    while t <= duration_s:
        sensors, physical, prev_ins_error, prev_lidar_error = generate_timestep_sensors(t, rng, prev_ins_error, prev_lidar_error)

        fusion = fuse_sensors(sensors, reliability_history=reliability_history, config=config)
        confidence = compute_confidence(fusion, sensors, config=config)
        reliability_history = update_reliability_history(reliability_history, sensors, config=config)

        err = fused_position_error(physical["ins_error_m"], physical["lidar_error_m"])
        reasons = "; ".join(confidence["reasons"][:2]) if confidence["reasons"] else "OK"

        q_by_name = {s["sensor"]: s["quality"] for s in sensors}
        print(f"{t:<7.0f}{q_by_name['INS']:<8.3f}{q_by_name['LIDAR']:<9.3f}{q_by_name['QMAG']:<8.3f}"
              f"{confidence['level']:<12}{err:<13.3f}{reasons}")

        results.append({
            "t_s": t,
            "sensors": sensors,
            "physical": physical,
            "fusion": fusion,
            "confidence": confidence,
            "fused_position_error_m": round(err, 3),
        })
        t += dt

    # --- Summary ---
    levels = [r["confidence"]["level"] for r in results]
    high = levels.count("HIGH")
    medium = levels.count("MEDIUM")
    low = levels.count("LOW")
    total = len(levels)

    print("\n" + "=" * 78)
    print("CONFIDENCE SUMMARY")
    print("=" * 78)
    print(f"Total time steps: {total}")
    print(f"HIGH:   {high} ({high/total*100:.0f}%)")
    print(f"MEDIUM: {medium} ({medium/total*100:.0f}%)")
    print(f"LOW:    {low} ({low/total*100:.0f}%)")

    qmag_detectable = sum(1 for r in results if r["sensors"][2]["detected"])
    print(f"\nMagnetometer anomaly detectable: {qmag_detectable}/{total} steps "
          f"({qmag_detectable/total*100:.0f}%) -- outside ferrous-equipment zones")

    # Early-warning narrative: uses the same early_warning_summary() that a
    # real NORCAT run (ground_truth_compare.py) will use against measured
    # error -- here fed with the simulated fused_position_error_m instead
    # of a real ground-truth comparison, so the metric definition is
    # identical between the simulated run and a future real one.
    confidence_trace = [{"t_s": r["t_s"], "level": r["confidence"]["level"]} for r in results]
    error_series = [{"t_s": r["t_s"], "error_m": r["fused_position_error_m"]} for r in results]
    ew = early_warning_summary(confidence_trace, error_series, error_threshold_m=1.0)

    if ew.get("warning_found"):
        print(f"\nFirst sustained confidence degradation at t={ew['warning_t_s']:.0f}s "
              f"({ew['warning_t_s']/60:.1f} min in), fused position error only "
              f"{ew['warning_error_m']:.2f}m.")
        print(f"By end of run (t={ew['final_t_s']:.0f}s), unflagged raw error would have reached "
              f"{ew['final_error_m']:.2f}m. The confidence layer surfaced the problem {ew['lead_time_min']:.1f} "
              f"minutes before error became severe -- that lead time is the operational value: time for an "
              f"operator to intervene before trusting a position that has quietly become unreliable.")
    else:
        print("\nNo sustained confidence degradation detected in this run.")

    print("\nReminder: all sensor streams above are SIMULATED (see module docstring).")
    print("The fusion/confidence/reliability CODE is the real, validated Ananta Meridian engine.")

    # --- Write outputs ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(out_dir, f"{timestamp}_norcat_testbed_simulated.json")
    csv_path = os.path.join(out_dir, f"{timestamp}_norcat_testbed_simulated.csv")

    with open(json_path, "w") as f:
        json.dump({
            "meta": {
                "title": "Ananta Meridian -- NORCAT Underground Testbed (SIMULATED)",
                "status": "SIMULATED -- not NORCAT facility data",
                "duration_s": duration_s,
                "dt_s": dt,
                "config_path": config_path,
                "engine": "data_fusion.fusion_engine / confidence_engine / reliability_memory (real, unmodified)",
            },
            "summary": {"high": high, "medium": medium, "low": low, "total": total},
            "early_warning": ew,
            "results": results,
        }, f, indent=2)

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t_s", "ins_quality", "lidar_quality", "qmag_quality", "qmag_detected",
                          "confidence_level", "fused_position_error_m", "reasons"])
        for r in results:
            q = {s["sensor"]: s for s in r["sensors"]}
            writer.writerow([
                r["t_s"], q["INS"]["quality"], q["LIDAR"]["quality"], q["QMAG"]["quality"],
                q["QMAG"]["detected"], r["confidence"]["level"], r["fused_position_error_m"],
                "; ".join(r["confidence"]["reasons"]),
            ])

    print(f"\nResults written:\n  {json_path}\n  {csv_path}")
    return results


if __name__ == "__main__":
    run()
