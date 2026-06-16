"""
Ananta Meridian — REST API Server
==================================
Zero-dependency (stdlib-only) HTTP wrapper around the fusion + confidence +
LLM operator guidance pipeline.

Endpoints
---------
  POST /api/v1/assess           Full pipeline: fusion + confidence + LLM guidance
  POST /api/v1/fusion           Just fusion + confidence (no LLM call)
  GET  /api/v1/scenarios        List available scenarios
  POST /api/v1/scenarios/run    Run a named scenario end-to-end
  GET  /api/v1/health           Liveness + version probe

Run
---
  python api_server.py                # default port 8420
  python api_server.py --port 9000

All requests/responses are JSON. CORS is permissive (Access-Control-Allow-Origin: *)
so a browser-side dashboard can call it without a proxy.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

# ── Ananta core imports ─────────────────────────────────────────────────────
from data_fusion import config as cfg_module
from data_fusion.scenarios import SCENARIOS
from data_fusion.fusion_engine import fuse_sensors
from data_fusion.confidence_engine import compute_confidence
from data_fusion.reliability_memory import update_reliability_history
from data_fusion import baselines
from data_fusion.kalman_baseline import kalman_filter, reset_kalman_state

VERSION = "0.3.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("api_server")

# Mapping of method name -> fusion callable. Mirrors experiments/runner.py
# but kept independent so the API can stand alone.
FUSION_METHODS = {
    "confidence_weighted": fuse_sensors,
    "simple_average": baselines.simple_average,
    "majority_vote": baselines.majority_vote,
    "best_quality_only": baselines.best_quality_only,
    "kalman_filter": kalman_filter,
}

_STATEFUL_METHODS = {"kalman_filter"}


# ── helpers ─────────────────────────────────────────────────────────────────

def _validate_sensors(sensors) -> None:
    if not isinstance(sensors, list):
        raise ValueError("'sensors' must be a list")
    if not sensors:
        raise ValueError("'sensors' must not be empty")
    required = {"sensor", "detected", "quality", "latency"}
    for i, s in enumerate(sensors):
        if not isinstance(s, dict):
            raise ValueError(f"sensors[{i}] must be an object")
        missing = required - set(s.keys())
        if missing:
            raise ValueError(f"sensors[{i}] missing keys: {sorted(missing)}")


def _run_fusion(sensors: list, method: str, config: dict) -> dict:
    """Run a single fusion step. Resets stateful methods so each request is
    independent (no leaking Kalman state between unrelated callers)."""
    if method not in FUSION_METHODS:
        raise ValueError(
            f"unknown method '{method}'. Available: {sorted(FUSION_METHODS)}"
        )

    if method in _STATEFUL_METHODS:
        reset_kalman_state()

    fuse_fn = FUSION_METHODS[method]
    if method == "confidence_weighted":
        # Fresh reliability history per request so callers don't get leakage.
        return fuse_fn(sensors, reliability_history={}, config=config)
    if method == "kalman_filter":
        return fuse_fn(sensors, config=config)
    return fuse_fn(sensors)


def _confidence_payload(fusion: dict, confidence: dict) -> dict:
    """Shape the confidence layer in a form the LLM operator layer expects.
    The LLM layer reads keys like confidence_level / weighted_score / reasons /
    recommended_actions / fused_detection — flatten them onto fusion."""
    return {
        **fusion,
        "confidence_level": confidence["level"],
        "weighted_score": confidence["weighted_score"],
        "reasons": confidence["reasons"],
        "recommended_actions": confidence["actions"],
    }


def _llm_guidance(fusion: dict, confidence: dict, sensors: list, mission_context: str) -> dict:
    """Try the real LLM, fall back to rule-based on any failure (incl. import)."""
    flattened = _confidence_payload(fusion, confidence)
    try:
        from llm_operator_layer import generate_operator_guidance
        return generate_operator_guidance(
            fusion_result=flattened,
            sensor_data=sensors,
            mission_context=mission_context,
        )
    except Exception as exc:  # noqa: BLE001 — last-resort fallback path
        logger.warning("LLM operator layer unavailable: %s — using local fallback", exc)
        try:
            from llm_operator_layer import _rule_based_fallback
            result = _rule_based_fallback(flattened, sensors, mission_context)
            result["_error"] = f"ImportOrRuntimeError: {exc}"
            return result
        except Exception as inner:  # noqa: BLE001
            # Absolute last-resort inline fallback.
            return {
                "operator_summary": (
                    f"Confidence {confidence['level']}; fused_detection="
                    f"{fusion['fused_detection']}; score={confidence['weighted_score']}."
                ),
                "threat_indicators": confidence["reasons"] or ["None identified"],
                "recommended_actions": confidence["actions"] or ["Continue monitoring"],
                "confidence_rationale": "; ".join(confidence["reasons"]) or confidence["level"],
                "escalation_required": confidence["level"] == "LOW",
                "_source": "inline_fallback",
                "_error": f"{exc}; secondary: {inner}",
            }


def _run_scenario(scenario_name: str, method: str, config: dict) -> dict:
    if scenario_name not in SCENARIOS:
        raise ValueError(
            f"unknown scenario '{scenario_name}'. Available: {sorted(SCENARIOS)}"
        )
    if method not in FUSION_METHODS:
        raise ValueError(
            f"unknown method '{method}'. Available: {sorted(FUSION_METHODS)}"
        )

    scenario = SCENARIOS[scenario_name]
    fuse_fn = FUSION_METHODS[method]
    ground_truths = scenario["ground_truth"]

    # Per-run state isolation
    if method in _STATEFUL_METHODS:
        reset_kalman_state()
    reliability_history: dict = {}

    steps_out = []
    for i, sensor_data in enumerate(scenario["steps"]):
        gt = ground_truths[i] if i < len(ground_truths) else None

        if method == "confidence_weighted":
            fusion = fuse_fn(sensor_data, reliability_history=reliability_history, config=config)
        elif method == "kalman_filter":
            fusion = fuse_fn(sensor_data, config=config)
        else:
            fusion = fuse_fn(sensor_data)

        confidence = compute_confidence(fusion, sensor_data, config=config)

        if method == "confidence_weighted":
            reliability_history = update_reliability_history(
                reliability_history, sensor_data, config=config
            )

        correct = None if gt is None else (fusion["fused_detection"] == gt)
        steps_out.append({
            "step": i + 1,
            "ground_truth": gt,
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

    comparable = [s for s in steps_out if s["ground_truth"] is not None]
    accuracy = (
        round(sum(1 for s in comparable if s["correct"]) / len(comparable), 3)
        if comparable else None
    )
    false_high = sum(
        1 for s in steps_out
        if s["ground_truth"] is not None and not s["correct"] and s["confidence_level"] == "HIGH"
    )
    collapse_step = next((s["step"] for s in steps_out if s["confidence_level"] == "LOW"), None)
    levels = [s["confidence_level"] for s in steps_out]
    transitions = sum(1 for i in range(1, len(levels)) if levels[i] != levels[i - 1])

    summary = {
        "total_steps": len(steps_out),
        "accuracy": accuracy,
        "false_high_confidence_count": false_high,
        "confidence_collapse_step": collapse_step,
        "confidence_transitions": transitions,
        "confidence_level_counts": {
            level: sum(1 for s in steps_out if s["confidence_level"] == level)
            for level in ("HIGH", "MEDIUM", "LOW")
        },
    }

    return {
        "scenario": scenario_name,
        "scenario_description": scenario["description"],
        "method": method,
        "steps": steps_out,
        "summary": summary,
    }


# ── HTTP layer ──────────────────────────────────────────────────────────────

class AnantaHandler(BaseHTTPRequestHandler):
    server_version = f"AnantaMeridianAPI/{VERSION}"

    # quieter access log — route through python logging
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        logger.info("%s - %s", self.address_string(), format % args)

    # ── response helpers ────────────────────────────────────────────────────
    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str, detail: str | None = None) -> None:
        payload = {"error": message}
        if detail:
            payload["detail"] = detail
        self._send_json(status, payload)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON body: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("request body must be a JSON object")
        return data

    # ── HTTP verbs ──────────────────────────────────────────────────────────
    def do_OPTIONS(self) -> None:  # noqa: N802 (stdlib API)
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        try:
            if self.path == "/api/v1/health":
                return self._send_json(200, {
                    "status": "ok",
                    "version": VERSION,
                    "methods": sorted(FUSION_METHODS),
                    "scenarios": sorted(SCENARIOS),
                })

            if self.path == "/api/v1/scenarios":
                return self._send_json(200, {
                    "scenarios": [
                        {"name": name, "description": s["description"], "steps": len(s["steps"])}
                        for name, s in SCENARIOS.items()
                    ]
                })

            return self._send_error(404, f"no route for GET {self.path}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("GET %s failed", self.path)
            return self._send_error(500, "internal server error", str(exc))

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/api/v1/fusion":
                return self._handle_fusion()
            if self.path == "/api/v1/assess":
                return self._handle_assess()
            if self.path == "/api/v1/scenarios/run":
                return self._handle_scenario_run()
            return self._send_error(404, f"no route for POST {self.path}")
        except ValueError as exc:
            return self._send_error(400, "bad request", str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.error("POST %s failed: %s\n%s", self.path, exc, traceback.format_exc())
            return self._send_error(500, "internal server error", str(exc))

    # ── route handlers ──────────────────────────────────────────────────────
    def _handle_fusion(self) -> None:
        body = self._read_json_body()
        sensors = body.get("sensors")
        method = body.get("method", "confidence_weighted")
        _validate_sensors(sensors)

        config = self.server.app_config  # type: ignore[attr-defined]
        fusion = _run_fusion(sensors, method, config)
        confidence = compute_confidence(fusion, sensors, config=config)

        self._send_json(200, {
            "method": method,
            "fusion": fusion,
            "confidence": confidence,
        })

    def _handle_assess(self) -> None:
        body = self._read_json_body()
        sensors = body.get("sensors")
        method = body.get("method", "confidence_weighted")
        mission_context = body.get("mission_context", "Arctic maritime")
        _validate_sensors(sensors)

        config = self.server.app_config  # type: ignore[attr-defined]
        fusion = _run_fusion(sensors, method, config)
        confidence = compute_confidence(fusion, sensors, config=config)
        guidance = _llm_guidance(fusion, confidence, sensors, mission_context)

        self._send_json(200, {
            "method": method,
            "mission_context": mission_context,
            "fusion": fusion,
            "confidence": confidence,
            "operator_guidance": guidance,
        })

    def _handle_scenario_run(self) -> None:
        body = self._read_json_body()
        scenario = body.get("scenario")
        method = body.get("method", "confidence_weighted")
        if not scenario:
            raise ValueError("'scenario' is required")

        config = self.server.app_config  # type: ignore[attr-defined]
        result = _run_scenario(scenario, method, config)
        self._send_json(200, result)


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Allow concurrent requests so a slow LLM call doesn't block /health."""
    daemon_threads = True
    allow_reuse_address = True


# ── entry point ─────────────────────────────────────────────────────────────

def build_server(host: str, port: int) -> ThreadingHTTPServer:
    config = cfg_module.load(None)
    server = ThreadingHTTPServer((host, port), AnantaHandler)
    server.app_config = config  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Ananta Meridian REST API")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8420, help="Bind port (default: 8420)")
    args = parser.parse_args()

    server = build_server(args.host, args.port)
    logger.info(
        "Ananta Meridian API v%s listening on http://%s:%d",
        VERSION, args.host, args.port,
    )
    logger.info("Methods: %s", sorted(FUSION_METHODS))
    logger.info("Scenarios: %s", sorted(SCENARIOS))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
