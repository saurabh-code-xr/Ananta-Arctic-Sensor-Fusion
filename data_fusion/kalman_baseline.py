"""
Discrete Kalman filter baseline for binary detection state.

This is a more credible benchmark than majority_vote / simple_average for
multi-sensor fusion. It treats the (probabilistic) detection state as a
1-D continuous random variable in [0, 1] with sensor observations weighted
by their measurement noise (derived from quality and freshness).

Why include this
----------------
The original repo only benchmarks confidence_weighted fusion against three
toy baselines (simple_average, majority_vote, best_quality_only). Any
reviewer with a sensor-fusion background will ask "how does this compare
to a Kalman filter?" — the standard tool for this problem class. Until
that comparison exists, the "confidence-weighted fusion adds value"
claim is not credibly defensible.

This is intentionally a simple scalar Kalman, not a full multi-target
tracker. Per-step it runs:

  Predict:  x = F * x;   P = F * P * F + Q
  Update:   for each sensor obs z_i with variance R_i:
              K = P / (P + R_i)
              x = x + K * (z_i - x)
              P = (1 - K) * P

Sensor variance R_i = sensor_variance_floor + (1 - quality_i * freshness_i) * variance_scale.
Higher quality + lower latency => lower R => more weight in update.

Detection threshold defaults to 0.5 on the posterior mean.
"""

from __future__ import annotations
from data_fusion.utils import freshness_factor


# Module-level state holder for repeatable runs. Use KalmanBaseline class
# directly when you need multiple parallel filters.
class KalmanBaseline:
    def __init__(
        self,
        process_variance: float = 0.05,
        sensor_variance_floor: float = 0.02,
        variance_scale: float = 0.5,
        threshold: float = 0.5,
        decay: float = 1.0,
    ):
        # Initial state: 0.5 prior (uniform belief), wide covariance
        self.x = 0.5
        self.P = 1.0
        self.Q = process_variance
        self.R_floor = sensor_variance_floor
        self.R_scale = variance_scale
        self.threshold = threshold
        self.F = decay  # 1.0 = persistent target, <1 = mean-reverting

    def step(self, sensor_data: list, config: dict | None = None) -> dict:
        if not sensor_data:
            return self._empty()

        # Predict step
        self.x = self.F * self.x
        self.P = self.F * self.P * self.F + self.Q

        per_sensor = {}
        for s in sensor_data:
            name = s["sensor"]
            q = float(s["quality"])
            lat = float(s["latency"])
            detected = bool(s["detected"])
            freshness = freshness_factor(lat, config=config)

            # Observation in [0, 1]
            z = 1.0 if detected else 0.0

            # Trust score in (0, 1] — used to scale measurement variance
            trust = max(1e-3, q * freshness)
            R = self.R_floor + (1.0 - trust) * self.R_scale

            # Kalman update
            K = self.P / (self.P + R)
            self.x = self.x + K * (z - self.x)
            self.P = (1.0 - K) * self.P

            per_sensor[name] = {
                "quality": round(q, 3),
                "latency": lat,
                "freshness_factor": round(freshness, 3),
                "kalman_gain": round(K, 3),
                "measurement_variance": round(R, 3),
                "detected": detected,
                "final_weight": round(K, 3),  # alias for runner compat
            }

        # Clamp posterior to [0, 1]
        self.x = max(0.0, min(1.0, self.x))

        score = self.x
        detections = [bool(s["detected"]) for s in sensor_data]
        return {
            "detected_count": sum(detections),
            "avg_quality": round(sum(float(s["quality"]) for s in sensor_data) / len(sensor_data), 3),
            "avg_latency": round(sum(float(s["latency"]) for s in sensor_data) / len(sensor_data), 1),
            "raw_weighted_detection_score": round(score, 3),
            "weighted_detection_score": round(score, 3),
            "fused_detection": score >= self.threshold,
            "per_sensor_weights": per_sensor,
            "disagreement": len(set(detections)) > 1,
            "disagreement_penalty": 1.0,
            "kalman_state_variance": round(self.P, 4),
            "kalman_state_mean": round(self.x, 3),
        }

    def _empty(self) -> dict:
        return {
            "detected_count": 0,
            "avg_quality": 0.0,
            "avg_latency": 0.0,
            "raw_weighted_detection_score": round(self.x, 3),
            "weighted_detection_score": round(self.x, 3),
            "fused_detection": self.x >= self.threshold,
            "per_sensor_weights": {},
            "disagreement": False,
            "disagreement_penalty": 1.0,
            "kalman_state_variance": round(self.P, 4),
            "kalman_state_mean": round(self.x, 3),
        }


# Functional wrapper. The runner calls fusion methods as plain functions
# without state, so we expose a stateful version here that resets per run.
_GLOBAL_KALMAN: KalmanBaseline | None = None


def reset_kalman_state() -> None:
    """Reset the global Kalman filter — call at the start of each scenario."""
    global _GLOBAL_KALMAN
    _GLOBAL_KALMAN = None


def kalman_filter(sensor_data: list, config: dict | None = None, **_) -> dict:
    """
    Drop-in fusion method matching the runner's expected signature.

    Note: maintains state across calls — the runner is responsible for
    calling reset_kalman_state() between scenarios.
    """
    global _GLOBAL_KALMAN
    if _GLOBAL_KALMAN is None:
        cfg = (config or {}).get("fusion", {}).get("kalman", {})
        _GLOBAL_KALMAN = KalmanBaseline(
            process_variance=cfg.get("process_variance", 0.05),
            sensor_variance_floor=cfg.get("sensor_variance_floor", 0.02),
            variance_scale=cfg.get("variance_scale", 0.5),
            threshold=cfg.get("threshold", 0.5),
            decay=cfg.get("decay", 1.0),
        )
    return _GLOBAL_KALMAN.step(sensor_data, config=config)
