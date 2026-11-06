"""
Threshold calibration -- fits confidence_engine threshold values against
real labeled outcomes, instead of the hand-set defaults in config.yaml.

This is NOT machine learning. It's a grid search over the same threshold
parameters confidence_engine.compute_confidence() already accepts
(high_score, high_quality, high_latency_ceiling, medium_score,
medium_quality, medium_latency_ceiling), picking the combination that
best matches HIGH/MEDIUM/LOW against ground-truth-derived "true"
reliability labels. The reasoning logic in confidence_engine.py is
untouched -- only the numbers plugging into it change, and every
candidate threshold set and its score is reported, so the result is
fully auditable (no hidden learned weights, no black box).

CRITICAL -- read before trusting any output of this script:
This only produces a trustworthy calibration when run against REAL
labeled data: fusion results paired with REAL measured position error
from ground_truth_compare.py. Calibrating against the simulated NORCAT
testbed's drift model would just teach the thresholds to match this
project's own simulation assumptions, not reality -- the same failure
mode as training an ML model on your own simulator. The simulated-data
path below exists ONLY to prove the calibration mechanism runs
correctly; its output must never be used as a production config.yaml
until real labeled data (from NORCAT or elsewhere) replaces it. Every
run of this script against simulated input prints a loud warning to
that effect.

What "true label" means here: HIGH/MEDIUM/LOW is assigned to each time
step from MEASURED position error against fixed bands (--high-max-error,
--medium-max-error), not from the confidence engine's own output. Those
error bands ARE an operational judgment call about what error magnitude
is acceptable for this platform/environment -- they are not derived from
data, and must be stated explicitly alongside any calibration result.

Usage:
    python calibrate_thresholds.py path/to/run.json --high-max-error 1.0 --medium-max-error 5.0
"""

import argparse
import itertools
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from data_fusion.confidence_engine import compute_confidence, DEFAULT_THRESHOLDS

# Misclassification cost: calling something HIGH when it's truly LOW
# (dangerous overconfidence -- an operator trusts a position that's
# actually badly wrong) is penalized far more than the reverse (overly
# cautious). Asymmetric by design, mirroring actual operational risk
# rather than optimizing for raw accuracy alone.
_MISCLASS_COST = {
    ("HIGH", "LOW"): 10, ("HIGH", "MEDIUM"): 3,
    ("MEDIUM", "LOW"): 4, ("MEDIUM", "HIGH"): 1,
    ("LOW", "HIGH"): 1, ("LOW", "MEDIUM"): 1,
}


def label_steps_from_error(results: list, high_max_error_m: float, medium_max_error_m: float) -> list:
    labels = []
    for r in results:
        err = r["fused_position_error_m"]
        if err <= high_max_error_m:
            labels.append("HIGH")
        elif err <= medium_max_error_m:
            labels.append("MEDIUM")
        else:
            labels.append("LOW")
    return labels


def _cost(true_label: str, predicted_label: str) -> int:
    if true_label == predicted_label:
        return 0
    return _MISCLASS_COST.get((predicted_label, true_label), 2)


def evaluate_thresholds(fusion_results: list, sensor_lists: list, true_labels: list, thresholds: dict) -> dict:
    total_cost = 0
    correct = 0
    confusion = {}
    for fusion, sensors, true_label in zip(fusion_results, sensor_lists, true_labels):
        pred = compute_confidence(fusion, sensors, thresholds=thresholds)["level"]
        total_cost += _cost(true_label, pred)
        correct += int(pred == true_label)
        confusion[(true_label, pred)] = confusion.get((true_label, pred), 0) + 1
    n = len(true_labels)
    return {
        "accuracy": round(correct / n, 4) if n else 0.0,
        "total_cost": total_cost,
        "avg_cost": round(total_cost / n, 4) if n else 0.0,
        "n": n,
        "confusion": confusion,
    }


def grid_search_calibrate(
    fusion_results, sensor_lists, true_labels,
    score_grid=(0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9),
    quality_grid=(0.5, 0.6, 0.7, 0.8, 0.9),
    latency_grid=(150, 200, 300, 450, 600),
):
    """Brute-force grid search over the threshold space, scored by
    weighted misclassification cost (see _MISCLASS_COST), not raw
    accuracy. Returns (best_thresholds, best_eval, top5_candidates)."""
    candidates = []
    for high_score, high_quality, high_latency in itertools.product(score_grid, quality_grid, latency_grid):
        medium_score_opts = [s for s in score_grid if s < high_score] or [round(high_score * 0.7, 3)]
        medium_quality_opts = [q for q in quality_grid if q < high_quality] or [round(high_quality * 0.7, 3)]
        medium_latency_opts = [l for l in latency_grid if l > high_latency] or [round(high_latency * 1.5, 1)]
        for medium_score, medium_quality, medium_latency in itertools.product(
            medium_score_opts, medium_quality_opts, medium_latency_opts
        ):
            thresholds = {
                "high_score": high_score, "high_quality": high_quality, "high_latency_ceiling": high_latency,
                "medium_score": medium_score, "medium_quality": medium_quality, "medium_latency_ceiling": medium_latency,
                "low_quality_threshold": 0.5, "high_latency_threshold": high_latency,
            }
            result = evaluate_thresholds(fusion_results, sensor_lists, true_labels, thresholds)
            candidates.append((result["avg_cost"], thresholds, result))

    candidates.sort(key=lambda c: c[0])
    best_cost, best_thresholds, best_result = candidates[0]
    return best_thresholds, best_result, candidates[:5]


def run(json_path: str, high_max_error_m: float, medium_max_error_m: float, force_simulated_flag: bool = False):
    with open(json_path) as f:
        run_data = json.load(f)

    results = run_data["results"]
    fusion_results = [r["fusion"] for r in results]
    sensor_lists = [r["sensors"] for r in results]
    true_labels = label_steps_from_error(results, high_max_error_m, medium_max_error_m)

    is_simulated = force_simulated_flag or str(run_data.get("meta", {}).get("status", "")).startswith("SIMULATED")

    print("=" * 78)
    print("THRESHOLD CALIBRATION")
    print("=" * 78)
    if is_simulated:
        print("*** INPUT DATA IS SIMULATED. This run proves the calibration MECHANISM only. ***")
        print("*** Do NOT use this result as a production config.yaml. ***\n")

    print(f"True-label bands: HIGH <= {high_max_error_m}m, MEDIUM <= {medium_max_error_m}m, else LOW")
    print(f"Samples: {len(true_labels)}  (HIGH={true_labels.count('HIGH')}, "
          f"MEDIUM={true_labels.count('MEDIUM')}, LOW={true_labels.count('LOW')})")

    default_eval = evaluate_thresholds(fusion_results, sensor_lists, true_labels, DEFAULT_THRESHOLDS)
    print(f"\nDefault (hand-set) thresholds: accuracy={default_eval['accuracy']*100:.1f}%, "
          f"avg misclassification cost={default_eval['avg_cost']}")

    best_thresholds, best_eval, top5 = grid_search_calibrate(fusion_results, sensor_lists, true_labels)
    print(f"\nCalibrated thresholds: accuracy={best_eval['accuracy']*100:.1f}%, "
          f"avg misclassification cost={best_eval['avg_cost']}")
    print(f"Thresholds: {best_thresholds}")

    print("\nTop 5 candidates (avg_cost, accuracy, thresholds):")
    for cost, th, res in top5:
        print(f"  cost={cost:.3f} acc={res['accuracy']*100:.1f}%  "
              f"high=(score={th['high_score']}, quality={th['high_quality']}, latency<{th['high_latency_ceiling']}) "
              f"medium=(score={th['medium_score']}, quality={th['medium_quality']}, latency<{th['medium_latency_ceiling']})")

    print("\nConfusion (true -> predicted):")
    for (true, pred), count in sorted(best_eval["confusion"].items()):
        print(f"  {true:>6} -> {pred:<6}: {count}")

    n = len(true_labels)
    if n < 200:
        print(f"\nWARNING: only {n} labeled samples. Calibration from a small/narrow run can overfit to "
              f"that run's specific conditions -- treat as provisional until validated against a second, "
              f"independent run before updating any production config.")

    return best_thresholds, best_eval


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrate confidence_engine thresholds against labeled ground-truth data")
    parser.add_argument("json_path", help="Run JSON with results[].fusion, results[].sensors, results[].fused_position_error_m")
    parser.add_argument("--high-max-error", type=float, default=1.0, help="Max measured error (m) still counted HIGH-worthy")
    parser.add_argument("--medium-max-error", type=float, default=5.0, help="Max measured error (m) still counted MEDIUM-worthy")
    parser.add_argument("--simulated", action="store_true", help="Force the simulated-data warning on (auto-detected from meta.status too)")
    args = parser.parse_args()
    run(args.json_path, args.high_max_error, args.medium_max_error, args.simulated)
