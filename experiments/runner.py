"""
Experiment runner — repeatable, logged, comparable.

Runs a named scenario (or live adapter) through a named fusion method,
computes per-step and summary metrics, and saves results to JSON.

Usage (module):
    from experiments.runner import run_experiment
    result = run_experiment("arctic_sensor_dropout", method="confidence_weighted")

Usage (CLI):
    python run_experiment.py --scenario arctic_sensor_dropout --method confidence_weighted
    python run_experiment.py --compare --scenario stale_data
    python run_experiment.py --source noaa
"""

import json
import os
from datetime import datetime

from data_fusion import config as cfg_module
from data_fusion.logger import get_logger, setup_logging
from data_fusion.scenarios import SCENARIOS
from data_fusion.fusion_engine import fuse_sensors
from data_fusion.confidence_engine import compute_confidence
from data_fusion.reliability_memory import update_reliability_history
from data_fusion import baselines
from data_fusion.kalman_baseline import kalman_filter, reset_kalman_state
from experiments.metrics import detection_metrics, roc_curve
from llm_operator_layer import generate_operator_guidance

logger = get_logger("runner")

FUSION_METHODS = {
    "confidence_weighted": fuse_sensors,
    "simple_average": baselines.simple_average,
    "majority_vote": baselines.majority_vote,
    "best_quality_only": baselines.best_quality_only,
    "kalman_filter": kalman_filter,
}

# Methods that maintain state across steps and need a per-run reset hook.
_STATEFUL_METHODS = {"kalman_filter"}


def _setup_from_config() -> dict:
    """Load config and initialise logging from it."""
    config = cfg_module.get()
    sys_cfg = config.get("system", {})
    setup_logging(
        level=sys_cfg.get("log_level", "INFO"),
        log_to_file=sys_cfg.get("log_to_file", False),
        log_file=sys_cfg.get("log_file", "logs/fusion.log"),
    )
    return config


def _accuracy(steps: list[dict]) -> float:
    comparable = [s for s in steps if s["ground_truth"] is not None]
    if not comparable:
        return 0.0
    return round(sum(1 for s in comparable if s["correct"]) / len(comparable), 3)


def _false_high_confidence(steps: list[dict]) -> int:
    return sum(
        1 for s in steps
        if s["ground_truth"] is not None and not s["correct"] and s["confidence_level"] == "HIGH"
    )


def _confidence_collapse_step(steps: list[dict]) -> int | None:
    for s in steps:
        if s["confidence_level"] == "LOW":
            return s["step"]
    return None


def _confidence_transitions(steps: list[dict]) -> int:
    levels = [s["confidence_level"] for s in steps]
    return sum(1 for i in range(1, len(levels)) if levels[i] != levels[i - 1])


def run_experiment(
    scenario_name: str,
    method: str = "confidence_weighted",
    save: bool = True,
    config: dict | None = None,
    llm_enabled: bool = False,
    mission_context: str = "Defence sensor fusion experiment",
) -> dict:
    """
    Run a scenario through a fusion method and return structured results.

    Parameters
    ----------
    scenario_name : key in data_fusion.scenarios.SCENARIOS
    method        : one of FUSION_METHODS keys
    save          : write results JSON to results/ directory
    config        : optional config dict (loads from config.yaml if None)
    """
    if config is None:
        config = _setup_from_config()

    if scenario_name not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario_name}'. Available: {list(SCENARIOS)}")
    if method not in FUSION_METHODS:
        raise ValueError(f"Unknown method '{method}'. Available: {list(FUSION_METHODS)}")

    scenario = SCENARIOS[scenario_name]
    fuse_fn = FUSION_METHODS[method]
    ground_truths = scenario["ground_truth"]

    logger.info("Running experiment: scenario=%s method=%s", scenario_name, method)

    if method in _STATEFUL_METHODS:
        reset_kalman_state()

    reliability_history: dict = {}
    step_results = []

    for i, sensor_data in enumerate(scenario["steps"]):
        ground_truth = ground_truths[i] if i < len(ground_truths) else None
        if method == "confidence_weighted":
            kwargs = {"reliability_history": reliability_history, "config": config}
        elif method == "kalman_filter":
            kwargs = {"config": config}
        else:
            kwargs = {}

        fusion = fuse_fn(sensor_data, **kwargs)
        confidence = compute_confidence(fusion, sensor_data, config=config)

        if method == "confidence_weighted":
            reliability_history = update_reliability_history(reliability_history, sensor_data, config=config)

        correct = None if ground_truth is None else (fusion["fused_detection"] == ground_truth)

        step_results.append({
            "step": i + 1,
            "ground_truth": ground_truth,
            "fused_detection": fusion["fused_detection"],
            "correct": correct,
            "confidence_level": confidence["level"],
            "weighted_score": fusion["weighted_detection_score"],
            "avg_quality": fusion["avg_quality"],
            "avg_latency": fusion["avg_latency"],
            "disagreement": fusion["disagreement"],
            "confidence_reasons": confidence["reasons"],
            "confidence_actions": confidence["actions"],
        })

    summary = {
        "total_steps": len(step_results),
        "accuracy": _accuracy(step_results),
        "false_high_confidence_count": _false_high_confidence(step_results),
        "confidence_collapse_step": _confidence_collapse_step(step_results),
        "confidence_transitions": _confidence_transitions(step_results),
        "confidence_level_counts": {
            level: sum(1 for s in step_results if s["confidence_level"] == level)
            for level in ("HIGH", "MEDIUM", "LOW")
        },
        **detection_metrics(step_results),
    }

    # LLM operator guidance -- runs once on the final fused step
    llm_guidance = None
    if llm_enabled and step_results:
        last = step_results[-1]
        llm_guidance = generate_operator_guidance(
            fusion_result={
                "confidence_level":    last["confidence_level"],
                "weighted_score":      last["weighted_score"],
                "fused_detection":     last["fused_detection"],
                "reasons":             last["confidence_reasons"],
                "recommended_actions": last["confidence_actions"],
            },
            sensor_data=scenario["steps"][-1],
            mission_context=mission_context,
        )
        logger.info("LLM guidance generated (source=%s)", llm_guidance.get("_source"))

    timestamp = datetime.now().isoformat(timespec="seconds")
    experiment_id = f"{timestamp[:10].replace('-', '')}_{scenario_name}_{method}"

    result = {
        "experiment_id":      experiment_id,
        "scenario":           scenario_name,
        "scenario_description": scenario["description"],
        "method":             method,
        "mission_context":    mission_context,
        "llm_enabled":        llm_enabled,
        "timestamp":          timestamp,
        "steps":              step_results,
        "summary":            summary,
        "llm_guidance":       llm_guidance,
    }

    if save:
        results_dir = config.get("experiment", {}).get("results_dir", "results")
        os.makedirs(results_dir, exist_ok=True)
        filepath = os.path.join(results_dir, f"{experiment_id}.json")
        with open(filepath, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info("Results saved to %s", filepath)

    return result


def run_from_steps(
    steps: list[list[dict]],
    source_name: str = "live",
    method: str = "confidence_weighted",
    save: bool = True,
    config: dict | None = None,
    llm_enabled: bool = False,
    mission_context: str = "Live sensor fusion",
) -> dict:
    """
    Run fusion on externally provided time steps (from an adapter).

    Used for live API data (NOAA, OpenWeather, CSV) where there is no ground truth.
    """
    if config is None:
        config = _setup_from_config()

    if method not in FUSION_METHODS:
        raise ValueError(f"Unknown method '{method}'.")

    fuse_fn = FUSION_METHODS[method]
    logger.info("Running live experiment: source=%s method=%s steps=%d", source_name, method, len(steps))

    reliability_history: dict = {}
    step_results = []

    for i, sensor_data in enumerate(steps):
        kwargs = {"reliability_history": reliability_history, "config": config} if method == "confidence_weighted" else {}
        fusion = fuse_fn(sensor_data, **kwargs)
        confidence = compute_confidence(fusion, sensor_data, config=config)

        if method == "confidence_weighted":
            reliability_history = update_reliability_history(reliability_history, sensor_data, config=config)

        step_results.append({
            "step": i + 1,
            "ground_truth": None,
            "fused_detection": fusion["fused_detection"],
            "correct": None,
            "confidence_level": confidence["level"],
            "weighted_score": fusion["weighted_detection_score"],
            "avg_quality": fusion["avg_quality"],
            "avg_latency": fusion["avg_latency"],
            "disagreement": fusion["disagreement"],
            "confidence_reasons": confidence["reasons"],
            "confidence_actions": confidence["actions"],
        })

    summary = {
        "total_steps": len(step_results),
        "accuracy": None,
        "false_high_confidence_count": None,
        "confidence_collapse_step": _confidence_collapse_step(step_results),
        "confidence_transitions": _confidence_transitions(step_results),
        "confidence_level_counts": {
            level: sum(1 for s in step_results if s["confidence_level"] == level)
            for level in ("HIGH", "MEDIUM", "LOW")
        },
    }

    # LLM operator guidance -- runs once on the final fused step
    llm_guidance = None
    if llm_enabled and step_results:
        last = step_results[-1]
        llm_guidance = generate_operator_guidance(
            fusion_result={
                "confidence_level":    last["confidence_level"],
                "weighted_score":      last["weighted_score"],
                "fused_detection":     last["fused_detection"],
                "reasons":             last["confidence_reasons"],
                "recommended_actions": last["confidence_actions"],
            },
            sensor_data=steps[-1],
            mission_context=mission_context,
        )
        logger.info("LLM guidance generated (source=%s)", llm_guidance.get("_source"))

    timestamp = datetime.now().isoformat(timespec="seconds")
    experiment_id = f"{timestamp[:10].replace('-', '')}_{source_name}_{method}"

    result = {
        "experiment_id":        experiment_id,
        "scenario":             source_name,
        "scenario_description": f"Live data from {source_name}",
        "method":               method,
        "mission_context":      mission_context,
        "llm_enabled":          llm_enabled,
        "timestamp":            timestamp,
        "steps":                step_results,
        "summary":              summary,
        "llm_guidance":         llm_guidance,
    }

    if save:
        results_dir = config.get("experiment", {}).get("results_dir", "results")
        os.makedirs(results_dir, exist_ok=True)
        filepath = os.path.join(results_dir, f"{experiment_id}.json")
        with open(filepath, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info("Results saved to %s", filepath)

    return result


def print_result(result: dict) -> None:
    """Print a human-readable experiment summary to stdout."""
    print(f"\n{'='*62}")
    print(f"EXPERIMENT : {result['experiment_id']}")
    print(f"Scenario   : {result['scenario']}")
    print(f"Method     : {result['method']}")
    print(f"{'='*62}")

    for step in result["steps"]:
        gt = step["ground_truth"]
        correct = step["correct"]
        flag = "" if correct is None else (" OK" if correct else " WRONG")
        print(
            f"  Step {step['step']}: {step['confidence_level']:<6} | "
            f"detected={str(step['fused_detection']):<5} | "
            f"score={step['weighted_score']:.3f} | "
            f"GT={'?' if gt is None else str(gt)}{flag}"
        )

    s = result["summary"]
    print(f"\n  Accuracy              : {str(s['accuracy']) if s['accuracy'] is not None else 'N/A (no ground truth)'}")
    if s.get("roc_auc") is not None:
        print(f"  ROC AUC               : {s['roc_auc']}")
    if s.get("precision") is not None:
        print(f"  Precision / Recall / F1: {s['precision']} / {s['recall']} / {s['f1']}")
    if s["false_high_confidence_count"] is not None:
        print(f"  False HIGH confidence : {s['false_high_confidence_count']}")
    print(f"  Confidence collapse   : step {s['confidence_collapse_step'] or 'never'}")
    print(f"  Confidence transitions: {s['confidence_transitions']}")
    print(f"  Level counts          : {s['confidence_level_counts']}")
    print()
