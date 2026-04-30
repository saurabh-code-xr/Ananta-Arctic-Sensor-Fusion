"""
Continuous freshness decay functions.

The original implementation (data_fusion/utils.py:freshness_factor) uses
a piecewise-constant step function. That has two problems:

  1. Discontinuities at bracket boundaries — a 1ms latency change can
     swing the freshness weight by 0.15. That's not physically realistic;
     sensor staleness degrades smoothly, not in steps.

  2. Hard to defend in a defence/maritime review — "why these brackets,
     why these factors?" has no principled answer.

This module provides continuous decay functions with configurable
parameters that can be calibrated against real sensor data.

Available decay models
----------------------
- exponential: f(t) = exp(-t / tau)
- linear:      f(t) = max(0, 1 - t / t_max)
- sigmoid:     f(t) = 1 / (1 + exp((t - t0) / k))

For backwards compatibility, the legacy bracket-based function in utils.py
remains available; this module is opt-in via config.
"""

from __future__ import annotations
import math
from typing import Callable

from data_fusion.logger import get_logger

logger = get_logger("freshness")


def exponential_decay(latency_ms: float, tau_ms: float = 500.0, floor: float = 0.05) -> float:
    """
    Exponential decay: f(t) = exp(-t / tau), clamped to [floor, 1.0].

    tau_ms controls how fast freshness decays. After `tau_ms` of latency,
    freshness drops to ~37%. After 3*tau_ms, freshness is ~5%.

    Default tau_ms = 500ms — appropriate for marine/satellite environments
    where 800–2000 ms latency is operationally normal, not degraded.
    For drone/terrestrial (low-latency) environments, set tau_ms: 200 in config.

    Parameters
    ----------
    latency_ms : non-negative latency in milliseconds
    tau_ms     : characteristic time constant (default 500ms — marine/satellite safe)
    floor      : minimum freshness value to prevent total trust collapse

    Returns
    -------
    Float in [floor, 1.0].
    """
    if latency_ms < 0:
        logger.warning("Negative latency %.1f received — clamping to 0.", latency_ms)
        latency_ms = 0.0
    if tau_ms <= 0:
        raise ValueError(f"tau_ms must be positive, got {tau_ms}")
    value = math.exp(-latency_ms / tau_ms)
    return max(floor, min(1.0, value))


def linear_decay(latency_ms: float, t_max_ms: float = 800.0, floor: float = 0.05) -> float:
    """
    Linear decay to zero at t_max_ms, clamped to [floor, 1.0].
    """
    if latency_ms < 0:
        latency_ms = 0.0
    if t_max_ms <= 0:
        raise ValueError(f"t_max_ms must be positive, got {t_max_ms}")
    value = 1.0 - (latency_ms / t_max_ms)
    return max(floor, min(1.0, value))


def sigmoid_decay(
    latency_ms: float,
    t0_ms: float = 300.0,
    k_ms: float = 80.0,
    floor: float = 0.05,
) -> float:
    """
    Sigmoid decay centered at t0_ms with slope controlled by k_ms.

    Useful when sensor freshness is roughly constant up to a "knee" latency
    (e.g. real-time tolerance) then drops off rapidly. k_ms controls the
    steepness around the knee.
    """
    if latency_ms < 0:
        latency_ms = 0.0
    if k_ms <= 0:
        raise ValueError(f"k_ms must be positive, got {k_ms}")
    value = 1.0 / (1.0 + math.exp((latency_ms - t0_ms) / k_ms))
    return max(floor, min(1.0, value))


_DECAY_MODELS: dict[str, Callable[..., float]] = {
    "exponential": exponential_decay,
    "linear": linear_decay,
    "sigmoid": sigmoid_decay,
}


def freshness_continuous(latency_ms: float, config: dict | None = None) -> float:
    """
    Configurable continuous freshness factor.

    Selects decay model and parameters from config.yaml under
    fusion.freshness_continuous, e.g.:

        fusion:
          freshness_continuous:
            model: exponential
            tau_ms: 250
            floor: 0.05

    Falls back to exponential decay with default tau_ms if no config.
    """
    if config is None:
        return exponential_decay(latency_ms)

    cfg = config.get("fusion", {}).get("freshness_continuous", {})
    model = cfg.get("model", "exponential")
    if model not in _DECAY_MODELS:
        logger.warning(
            "Unknown freshness model '%s' — falling back to exponential.", model
        )
        model = "exponential"

    fn = _DECAY_MODELS[model]
    # Pass through model-specific parameters, ignoring unknowns
    params = {k: v for k, v in cfg.items() if k != "model"}
    try:
        return fn(latency_ms, **params)
    except (TypeError, ValueError) as e:
        logger.warning(
            "Bad freshness params for model '%s': %s — using defaults.", model, e
        )
        return fn(latency_ms)
