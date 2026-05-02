"""
Monte Carlo synthetic data generator for calibration analysis.

For each scenario in data_fusion.scenarios.SCENARIOS, generate N randomized
variants by applying:
  - quality jitter: ±0.1 (uniform), clamped to [0, 1]
  - latency jitter: ±20% (uniform), clamped to >= 0
  - detection flip probability: 5% per sensor reading

Each variant is run through every fusion method, and per-step
(weighted_score, ground_truth, method, scenario) tuples are collected.
Steps with ground_truth == None (unknown / blackout) are skipped because
they cannot inform calibration.

Output: calibration/results.json
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path

from data_fusion import config as cfg_module
from data_fusion.scenarios import SCENARIOS
from data_fusion.fusion_engine import fuse_sensors
from data_fusion.baselines import simple_average, majority_vote, best_quality_only
from data_fusion.kalman_baseline import kalman_filter, reset_kalman_state
from data_fusion.reliability_memory import update_reliability_history

# Method registry — maps method name to (callable, needs_state_reset).
# Different methods take different kwargs; we route them in run_method().
METHODS: list[str] = [
    "confidence_weighted",
    "kalman_filter",
    "simple_average",
    "majority_vote",
    "best_quality_only",
]

N_VARIANTS_PER_SCENARIO = 100
QUALITY_JITTER = 0.1          # ± uniform
LATENCY_JITTER_FRAC = 0.20    # ±20%
FLIP_PROBABILITY = 0.05
RANDOM_SEED = 42


def jitter_step(
    step: list[dict],
    rng: random.Random,
) -> list[dict]:
    """Return a randomized copy of one timestep's sensor readings."""
    out = []
    for s in step:
        new = dict(s)
        # Quality jitter, clamped to [0, 1]
        q_delta = rng.uniform(-QUALITY_JITTER, QUALITY_JITTER)
        new["quality"] = max(0.0, min(1.0, float(s["quality"]) + q_delta))
        # Latency jitter, ±20%
        l_factor = 1.0 + rng.uniform(-LATENCY_JITTER_FRAC, LATENCY_JITTER_FRAC)
        new["latency"] = max(0.0, float(s["latency"]) * l_factor)
        # Detection flip
        if rng.random() < FLIP_PROBABILITY:
            new["detected"] = not bool(s["detected"])
        else:
            new["detected"] = bool(s["detected"])
        out.append(new)
    return out


def jitter_scenario(scenario: dict, rng: random.Random) -> list[list[dict]]:
    """Return a randomized copy of all timesteps for one scenario."""
    return [jitter_step(step, rng) for step in scenario["steps"]]


def run_method(
    method: str,
    variant_steps: list[list[dict]],
    config: dict,
) -> list[float]:
    """
    Run all timesteps of one variant through one fusion method.
    Returns list of weighted_detection_score per step (same length as variant_steps).
    """
    if method == "kalman_filter":
        reset_kalman_state()

    reliability_history: dict = {}
    scores: list[float] = []

    for step in variant_steps:
        if method == "confidence_weighted":
            res = fuse_sensors(
                step,
                reliability_history=reliability_history,
                config=config,
            )
            update_reliability_history(reliability_history, step, config=config)
        elif method == "kalman_filter":
            res = kalman_filter(step, config=config)
        elif method == "simple_average":
            res = simple_average(step)
        elif method == "majority_vote":
            res = majority_vote(step)
        elif method == "best_quality_only":
            res = best_quality_only(step)
        else:
            raise ValueError(f"Unknown method: {method}")

        scores.append(float(res["weighted_detection_score"]))

    return scores


def generate(
    n_variants: int = N_VARIANTS_PER_SCENARIO,
    seed: int = RANDOM_SEED,
    output_path: str | Path = "calibration/results.json",
) -> dict:
    """Run the full Monte Carlo sweep and persist results."""
    rng = random.Random(seed)
    config = cfg_module.get()

    samples: list[dict] = []
    counters = {m: 0 for m in METHODS}

    for scenario_name, scenario in SCENARIOS.items():
        ground_truths = scenario["ground_truth"]
        n_steps = len(scenario["steps"])

        for variant_idx in range(n_variants):
            variant_steps = jitter_scenario(scenario, rng)

            for method in METHODS:
                scores = run_method(method, variant_steps, config)

                for step_idx, score in enumerate(scores):
                    gt = ground_truths[step_idx] if step_idx < len(ground_truths) else None
                    if gt is None:
                        # Skip blackout / unknown steps — no calibration signal.
                        continue
                    samples.append({
                        "scenario": scenario_name,
                        "method": method,
                        "variant": variant_idx,
                        "step": step_idx,
                        "weighted_score": round(score, 6),
                        "ground_truth": bool(gt),
                    })
                    counters[method] += 1

        print(f"  scenario={scenario_name:<24} variants={n_variants}  steps/var={n_steps}")

    payload = {
        "config": {
            "n_variants_per_scenario": n_variants,
            "quality_jitter": QUALITY_JITTER,
            "latency_jitter_frac": LATENCY_JITTER_FRAC,
            "flip_probability": FLIP_PROBABILITY,
            "random_seed": seed,
            "methods": METHODS,
            "scenarios": list(SCENARIOS.keys()),
        },
        "counts_per_method": counters,
        "total_samples": len(samples),
        "samples": samples,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump(payload, f, indent=2)

    return payload


def main() -> None:
    print("=" * 72)
    print("Monte Carlo synthetic data generation for calibration analysis")
    print("=" * 72)
    print(f"Scenarios:        {list(SCENARIOS.keys())}")
    print(f"Methods:          {METHODS}")
    print(f"Variants/scen:    {N_VARIANTS_PER_SCENARIO}")
    print(f"Quality jitter:   ±{QUALITY_JITTER}")
    print(f"Latency jitter:   ±{LATENCY_JITTER_FRAC * 100:.0f}%")
    print(f"Flip probability: {FLIP_PROBABILITY * 100:.0f}%")
    print(f"Random seed:      {RANDOM_SEED}")
    print("-" * 72)
    payload = generate()
    print("-" * 72)
    print(f"Total samples written: {payload['total_samples']}")
    for m, c in payload["counts_per_method"].items():
        print(f"  {m:<22} {c} samples")
    print("Saved to calibration/results.json")


if __name__ == "__main__":
    main()
