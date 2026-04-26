"""
Scenario library — simulated degraded sensing scenarios.

Each scenario is a dict with:
  name        : identifier
  description : what real-world condition this models
  steps       : list of time-step sensor readings
  ground_truth: bool per step — is the target actually present?

Ground truth enables confidence calibration analysis:
  does HIGH confidence correlate with correct detection?
"""

SCENARIOS: dict[str, dict] = {}


# ── 1. Gradual Degradation ────────────────────────────────────────────────────
# Sensors degrade incrementally — reflects physical wear or environmental drift.
# Target is present throughout. Ground truth: always True.
SCENARIOS["gradual_degradation"] = {
    "name": "gradual_degradation",
    "description": (
        "All sensors degrade progressively over time. Models physical wear, "
        "icing, or environmental drift in an Arctic or maritime context. "
        "Target remains present throughout."
    ),
    "ground_truth": [True, True, True, True, True],
    "steps": [
        [
            {"sensor": "A", "detected": True,  "quality": 0.92, "latency": 100},
            {"sensor": "B", "detected": True,  "quality": 0.90, "latency": 110},
            {"sensor": "C", "detected": True,  "quality": 0.89, "latency": 105},
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.88, "latency": 120},
            {"sensor": "B", "detected": True,  "quality": 0.82, "latency": 130},
            {"sensor": "C", "detected": True,  "quality": 0.70, "latency": 180},
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.80, "latency": 150},
            {"sensor": "B", "detected": False, "quality": 0.75, "latency": 200},
            {"sensor": "C", "detected": True,  "quality": 0.62, "latency": 250},
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.65, "latency": 220},
            {"sensor": "B", "detected": False, "quality": 0.55, "latency": 420},
            {"sensor": "C", "detected": True,  "quality": 0.50, "latency": 500},
        ],
        [
            {"sensor": "A", "detected": False, "quality": 0.45, "latency": 500},
            {"sensor": "B", "detected": False, "quality": 0.35, "latency": 650},
            {"sensor": "C", "detected": True,  "quality": 0.40, "latency": 700},
        ],
    ],
}


# ── 2. Arctic Sensor Dropout ──────────────────────────────────────────────────
# Sensors fail one by one due to extreme cold. Latency spikes precede dropout.
# Target IS present — sensor failure ≠ target absence. System must not confuse the two.
SCENARIOS["arctic_sensor_dropout"] = {
    "name": "arctic_sensor_dropout",
    "description": (
        "Sensors drop out sequentially due to extreme cold or icing. "
        "Latency spikes precede full dropout. "
        "Target is present throughout — sensor failure must not be mistaken for target absence. "
        "Tests graceful degradation and confidence floor behaviour."
    ),
    "ground_truth": [True, True, True, True, True],
    "steps": [
        [
            {"sensor": "A", "detected": True,  "quality": 0.91, "latency": 105},
            {"sensor": "B", "detected": True,  "quality": 0.88, "latency": 115},
            {"sensor": "C", "detected": True,  "quality": 0.86, "latency": 110},
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.87, "latency": 120},
            {"sensor": "B", "detected": True,  "quality": 0.80, "latency": 140},
            {"sensor": "C", "detected": True,  "quality": 0.60, "latency": 420},  # C latency spikes
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.83, "latency": 130},
            {"sensor": "B", "detected": True,  "quality": 0.72, "latency": 300},  # B degrading
            {"sensor": "C", "detected": False, "quality": 0.30, "latency": 700},  # C near-dropout
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.75, "latency": 180},
            {"sensor": "B", "detected": False, "quality": 0.25, "latency": 800},  # B dropped
            {"sensor": "C", "detected": False, "quality": 0.10, "latency": 950},  # C dropped
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.55, "latency": 350},  # A degraded but holding
            {"sensor": "B", "detected": False, "quality": 0.15, "latency": 900},
            {"sensor": "C", "detected": False, "quality": 0.10, "latency": 1000},
        ],
    ],
}


# ── 3. Conflict / Spoofing ────────────────────────────────────────────────────
# One sensor reports the opposite of others — models a spoofing event or
# a miscalibrated sensor feeding false negatives into the picture.
# Target IS present. System must resist false negatives driven by one bad sensor.
SCENARIOS["conflict_spoofing"] = {
    "name": "conflict_spoofing",
    "description": (
        "One sensor is spoofed or miscalibrated and reports the opposite of the others. "
        "Models a spoofing event or adversarial interference in an autonomous sensing network. "
        "Target is present — system must maintain confidence despite disagreement."
    ),
    "ground_truth": [True, True, True, True, True],
    "steps": [
        [
            {"sensor": "A", "detected": True,  "quality": 0.90, "latency": 110},
            {"sensor": "B", "detected": True,  "quality": 0.88, "latency": 115},
            {"sensor": "C", "detected": True,  "quality": 0.87, "latency": 108},
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.89, "latency": 112},
            {"sensor": "B", "detected": True,  "quality": 0.86, "latency": 118},
            {"sensor": "C", "detected": False, "quality": 0.85, "latency": 110},  # C spoofed
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.88, "latency": 115},
            {"sensor": "B", "detected": False, "quality": 0.84, "latency": 120},  # B spoofed
            {"sensor": "C", "detected": False, "quality": 0.83, "latency": 112},  # C still spoofed
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.87, "latency": 118},  # A isolated
            {"sensor": "B", "detected": False, "quality": 0.85, "latency": 122},
            {"sensor": "C", "detected": False, "quality": 0.84, "latency": 115},
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.88, "latency": 110},  # sensors realign
            {"sensor": "B", "detected": True,  "quality": 0.86, "latency": 115},
            {"sensor": "C", "detected": True,  "quality": 0.85, "latency": 112},
        ],
    ],
}


# ── 4. Stale Data ─────────────────────────────────────────────────────────────
# All sensors report high quality but with increasing latency — data is old.
# Target IS present. Tests whether the system penalises stale data appropriately
# and does not produce false HIGH confidence from outdated readings.
SCENARIOS["stale_data"] = {
    "name": "stale_data",
    "description": (
        "Sensors maintain quality but latency rises sharply — data becomes stale. "
        "Models a comms degradation event or a network disruption. "
        "Tests whether the confidence system correctly penalises old data "
        "rather than treating high-quality-but-stale readings as trustworthy."
    ),
    "ground_truth": [True, True, True, True, False],
    "steps": [
        [
            {"sensor": "A", "detected": True,  "quality": 0.90, "latency": 100},
            {"sensor": "B", "detected": True,  "quality": 0.88, "latency": 105},
            {"sensor": "C", "detected": True,  "quality": 0.87, "latency": 102},
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.89, "latency": 250},
            {"sensor": "B", "detected": True,  "quality": 0.87, "latency": 280},
            {"sensor": "C", "detected": True,  "quality": 0.86, "latency": 260},
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.88, "latency": 500},
            {"sensor": "B", "detected": True,  "quality": 0.86, "latency": 520},
            {"sensor": "C", "detected": True,  "quality": 0.85, "latency": 510},
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.87, "latency": 700},
            {"sensor": "B", "detected": False, "quality": 0.85, "latency": 750},  # dropout
            {"sensor": "C", "detected": True,  "quality": 0.84, "latency": 720},
        ],
        [
            # Target has moved/left but stale data still shows detection — false positive risk
            {"sensor": "A", "detected": True,  "quality": 0.86, "latency": 900},
            {"sensor": "B", "detected": True,  "quality": 0.84, "latency": 950},
            {"sensor": "C", "detected": True,  "quality": 0.85, "latency": 920},
        ],
    ],
}


# ── 5. Full Sensor Failure ────────────────────────────────────────────────────
# Catastrophic failure — all sensors go down. Tests graceful degradation
# to LOW confidence and correct operator warning behaviour.
SCENARIOS["full_sensor_failure"] = {
    "name": "full_sensor_failure",
    "description": (
        "Catastrophic event causes all sensors to fail sequentially. "
        "Tests that the system gracefully degrades to LOW confidence "
        "and correctly advises the operator rather than producing false positives. "
        "Partial recovery at step 5."
    ),
    "ground_truth": [True, True, True, None, True],  # None = unknown during blackout
    "steps": [
        [
            {"sensor": "A", "detected": True,  "quality": 0.91, "latency": 108},
            {"sensor": "B", "detected": True,  "quality": 0.89, "latency": 112},
            {"sensor": "C", "detected": True,  "quality": 0.88, "latency": 110},
        ],
        [
            {"sensor": "A", "detected": True,  "quality": 0.70, "latency": 200},
            {"sensor": "B", "detected": False, "quality": 0.30, "latency": 600},  # B failing
            {"sensor": "C", "detected": True,  "quality": 0.65, "latency": 250},
        ],
        [
            {"sensor": "A", "detected": False, "quality": 0.25, "latency": 700},  # A failing
            {"sensor": "B", "detected": False, "quality": 0.15, "latency": 900},
            {"sensor": "C", "detected": False, "quality": 0.20, "latency": 800},  # C failing
        ],
        [
            # Full blackout — system has no reliable picture
            {"sensor": "A", "detected": False, "quality": 0.10, "latency": 1000},
            {"sensor": "B", "detected": False, "quality": 0.10, "latency": 1000},
            {"sensor": "C", "detected": False, "quality": 0.10, "latency": 1000},
        ],
        [
            # Partial recovery
            {"sensor": "A", "detected": True,  "quality": 0.65, "latency": 200},
            {"sensor": "B", "detected": False, "quality": 0.20, "latency": 800},
            {"sensor": "C", "detected": True,  "quality": 0.60, "latency": 220},
        ],
    ],
}
