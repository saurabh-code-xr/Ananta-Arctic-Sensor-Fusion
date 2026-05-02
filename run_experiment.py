"""
CLI entry point for running experiments.

Usage:
    python run_experiment.py --scenario arctic_sensor_dropout
    python run_experiment.py --scenario conflict_spoofing --method majority_vote
    python run_experiment.py --all
    python run_experiment.py --compare --scenario stale_data
    python run_experiment.py --source noaa
    python run_experiment.py --source openweather
    python run_experiment.py --source usgs
    python run_experiment.py --source csv --csv-file data/my_sensors.csv
    python run_experiment.py --config custom_config.yaml --scenario gradual_degradation

    # With LLM operator guidance (uses one Anthropic API call):
    python run_experiment.py --scenario arctic_sensor_dropout --llm
    python run_experiment.py --source noaa --llm --mission "Arctic weather station monitoring"
"""

import argparse
import sys

from data_fusion import config as cfg_module
from data_fusion.scenarios import SCENARIOS
from experiments.runner import FUSION_METHODS, run_experiment, run_from_steps, print_result


def run_all_scenarios(method: str, config: dict, llm_enabled: bool = False, mission_context: str = "") -> None:
    for name in SCENARIOS:
        result = run_experiment(name, method=method, config=config, llm_enabled=llm_enabled, mission_context=mission_context)
        print_result(result)


def compare_methods(scenario_name: str, config: dict) -> None:
    print(f"\nCOMPARISON — Scenario: {scenario_name}")
    print(f"{'Method':<25} {'Accuracy':>10} {'AUC':>8} {'F1':>6} {'False HIGH':>12} {'Collapse':>10}")
    print("-" * 78)
    for method in FUSION_METHODS:
        result = run_experiment(scenario_name, method=method, save=False, config=config)
        s = result["summary"]
        collapse = s["confidence_collapse_step"] or "-"
        acc = f"{s['accuracy']:.1%}" if s["accuracy"] is not None else "N/A"
        auc = f"{s['roc_auc']:.3f}" if s.get("roc_auc") is not None else "-"
        f1 = f"{s['f1']:.2f}" if s.get("f1") is not None else "-"
        print(f"  {method:<23} {acc:>10} {auc:>8} {f1:>6} {s['false_high_confidence_count']:>12} {str(collapse):>10}")
    print()


def run_live_source(source: str, method: str, csv_file: str | None, config: dict, llm_enabled: bool = False, mission_context: str = "") -> None:
    if source == "noaa":
        from data_fusion.adapters.noaa_adapter import build_noaa_adapter_from_config
        adapter = build_noaa_adapter_from_config(config)
    elif source == "openweather":
        from data_fusion.adapters.openweather_adapter import build_openweather_adapter_from_config
        adapter = build_openweather_adapter_from_config(config)
    elif source == "openaq":
        from data_fusion.adapters.openaq_adapter import build_openaq_adapter_from_config
        adapter = build_openaq_adapter_from_config(config)
    elif source == "usgs":
        from data_fusion.adapters.usgs_adapter import build_usgs_adapter_from_config
        adapter = build_usgs_adapter_from_config(config)
    elif source == "nws":
        from data_fusion.adapters.nws_adapter import build_nws_adapter_from_config
        adapter = build_nws_adapter_from_config(config)
    elif source == "csv":
        from data_fusion.adapters.csv_adapter import CSVAdapter
        cfg = config.get("sensors", {}).get("csv", {})
        file_path = csv_file or cfg.get("file_path", "data/sensor_readings.csv")
        adapter = CSVAdapter(
            file_path=file_path,
            sensor_col=cfg.get("sensor_col", "sensor_id"),
            detected_col=cfg.get("detected_col", "detected"),
            quality_col=cfg.get("quality_col", "quality"),
            latency_col=cfg.get("latency_col", "latency_ms"),
        )
    else:
        print(f"Unknown source '{source}'. Use: noaa | openweather | openaq | usgs | csv")
        sys.exit(1)

    steps = adapter.fetch()
    if not steps:
        print(f"No data returned from {source} adapter.")
        sys.exit(1)

    result = run_from_steps(steps, source_name=source, method=method, config=config, llm_enabled=llm_enabled, mission_context=mission_context)
    print_result(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ananta Meridian — Degraded Sensor Fusion Experiment Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--scenario", choices=list(SCENARIOS), help="Simulated scenario to run")
    parser.add_argument("--method", choices=list(FUSION_METHODS), default="confidence_weighted")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--compare", action="store_true", help="Compare all methods on one scenario")
    parser.add_argument("--source", choices=["noaa", "openweather", "openaq", "usgs", "csv", "nws"], help="Live data source")
    parser.add_argument("--csv-file", help="Path to CSV file (used with --source csv)")
    parser.add_argument("--config", default=None, help="Path to config YAML (default: config.yaml)")
    parser.add_argument("--no-save", action="store_true", help="Skip saving results to disk")
    parser.add_argument("--llm",     action="store_true",
                        help="Enable LLM operator guidance on final fused result (1 API call)")
    parser.add_argument("--mission", default="Defence sensor fusion",
                        help="Mission context string passed to LLM (use with --llm)")
    args = parser.parse_args()

    config = cfg_module.load(args.config)

    if args.all:
        run_all_scenarios(args.method, config, llm_enabled=args.llm, mission_context=args.mission)
    elif args.compare:
        if not args.scenario:
            parser.error("--compare requires --scenario")
        compare_methods(args.scenario, config)
    elif args.source:
        run_live_source(args.source, args.method, args.csv_file, config, llm_enabled=args.llm, mission_context=args.mission)
    elif args.scenario:
        result = run_experiment(args.scenario, method=args.method, save=not args.no_save, config=config, llm_enabled=args.llm, mission_context=args.mission)
        print_result(result)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
