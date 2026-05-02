# Ananta Meridian — Degraded Sensor Fusion

A software-first, hardware-agnostic, confidence-aware sensor fusion system for degraded environments.

**Current TRL:** 3 (proof of concept validated against real hardware data and live sensor feeds)

---

## What It Does

Combines inputs from multiple sensors operating under degraded conditions and produces a single fused detection output with an operator-facing confidence level (HIGH / MEDIUM / LOW) and plain-language CAF operator guidance via an integrated LLM reasoning layer.

Designed for:
- Arctic navigation and situational awareness
- Remote / maritime sensing environments
- Autonomous systems in comms-degraded or environmentally stressed conditions
- Any heterogeneous multi-sensor network where individual sensors are unreliable

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run a simulated scenario
python run_experiment.py --scenario arctic_sensor_dropout

# Compare all fusion methods on one scenario
python run_experiment.py --compare --scenario conflict_spoofing

# Run all scenarios
python run_experiment.py --all

# Use live NWS Arctic weather data (no API key required)
python run_experiment.py --source nws

# Use OpenWeatherMap live data (requires free API key)
python run_experiment.py --source openweather

# Use USGS live seismic data (no API key required)
python run_experiment.py --source usgs

# Use your own sensor CSV file
python run_experiment.py --source csv --csv-file data/your_sensors.csv

# Run Arctic AIS pipeline with LLM operator guidance
python analyze_arctic_ais.py --csv data/arctic_ais_parsed.csv --llm

# Run DJI drone pipeline with LLM operator guidance
python analyze_dji_flight.py --llm

# Run any scenario with LLM guidance and mission context
python run_experiment.py --scenario arctic_sensor_dropout --llm --mission "Northwest Passage patrol"
```

---

## Integration Guide for Hardware Partners

### Step 1: Understand the input format

The system accepts sensor readings in this format:

```python
sensor_data = [
    {"sensor": "A", "detected": True,  "quality": 0.85, "latency": 120},
    {"sensor": "B", "detected": False, "quality": 0.42, "latency": 380},
    {"sensor": "C", "detected": True,  "quality": 0.71, "latency": 210},
]
```

| Field | Type | Description |
|---|---|---|
| `sensor` | string | Unique sensor identifier |
| `detected` | bool | Did this sensor detect the target/event? |
| `quality` | float [0–1] | Self-reported or estimated signal quality |
| `latency` | float (ms) | Age of the reading in milliseconds |

### Step 2: Feed your data to the fusion engine

```python
from data_fusion.fusion_engine import fuse_sensors
from data_fusion.confidence_engine import compute_confidence
from data_fusion.reliability_memory import update_reliability_history

reliability_history = {}

# For each time step from your sensors:
sensor_data = your_sensor_reading_function()

fusion = fuse_sensors(sensor_data, reliability_history=reliability_history)
confidence = compute_confidence(fusion, sensor_data)

print(confidence["level"])   # HIGH / MEDIUM / LOW
print(confidence["actions"]) # Recommended operator actions

reliability_history = update_reliability_history(reliability_history, sensor_data)
```

### Step 3: Tune for your platform

Edit `config.yaml` to match your sensor characteristics:

```yaml
fusion:
  detection_threshold: 0.6    # lower = more sensitive to weak signals

  # Freshness decay — controls how latency reduces sensor trust weight.
  # Default: exponential with tau_ms=500 (marine/satellite safe).
  # At tau_ms latency, trust drops to ~37%. At 3×tau_ms, trust ≈ 5%.
  freshness_continuous:
    model: exponential
    tau_ms: 500    # marine/satellite default — increase for slower comms
    floor: 0.05    # minimum trust floor (never fully ignores a sensor)
  # For drone/terrestrial low-latency platforms, use tau_ms: 200

confidence:
  thresholds:
    high:
      min_score: 0.8
      max_latency_ms: 1000    # marine default — reduce for low-latency platforms
    medium:
      min_score: 0.5
      max_latency_ms: 2000
```

### Step 4: Plug in your data source

**Option A: CSV file** (for historical/pre-recorded sensor logs)

```bash
python run_experiment.py --source csv --csv-file /path/to/your/sensors.csv
```

CSV format:
```
timestamp,sensor_id,detected,quality,latency_ms
2024-01-01T00:00:00,LIDAR_1,True,0.87,115
2024-01-01T00:00:00,RADAR_1,False,0.43,420
```

**Option B: Live NWS Arctic weather (no key required)**

```bash
python run_experiment.py --source nws
```

**Option C: Direct Python integration**

```python
from data_fusion.adapters.csv_adapter import CSVAdapter

adapter = CSVAdapter("your_data.csv")
steps = adapter.fetch()  # returns list of time steps

from experiments.runner import run_from_steps
result = run_from_steps(steps, source_name="your_platform")
```

---

## Architecture

```
data_fusion/
├── utils.py                # Freshness factor, input validation (shared)
├── fusion_engine.py        # Confidence-weighted fusion core
├── confidence_engine.py    # HIGH/MEDIUM/LOW confidence evaluation
├── reliability_memory.py   # Per-sensor reliability tracking
├── scenarios.py            # Simulated degraded sensing scenarios (5)
├── baselines.py            # Naive baselines for benchmarking (3)
├── config.py               # Config loader (config.yaml)
├── logger.py               # Logging setup
└── adapters/
    ├── csv_adapter.py          # Pre-recorded sensor logs
    ├── noaa_adapter.py         # NOAA CDO historical weather (token required)
    ├── nws_adapter.py          # NWS live Arctic weather (no key required)
    ├── openweather_adapter.py  # OpenWeatherMap live data
    ├── usgs_adapter.py         # USGS live seismic data (no key required)
    └── openaq_adapter.py       # OpenAQ air quality network

llm_operator_layer.py       # LLM reasoning layer (claude-sonnet-4-5): converts
                            # fusion output into CAF operator guidance
                            # (operator_summary, threat_indicators,
                            # recommended_actions, confidence_rationale,
                            # escalation_required). Graceful fallback to
                            # rule-based output if API unavailable.

experiments/
└── runner.py           # Repeatable experiment runner + metrics

tests/                  # 133 tests, all passing
results/                # Experiment output (JSON)
config.yaml             # All tunable parameters
```

---

## Scenarios

| Scenario | Description | Ground truth |
|---|---|---|
| `gradual_degradation` | All sensors degrade progressively | Target present throughout |
| `arctic_sensor_dropout` | Sensors fail due to extreme cold | Target present throughout |
| `conflict_spoofing` | One sensor spoofed/miscalibrated | Target present throughout |
| `stale_data` | High quality but increasing latency | Mixed |
| `full_sensor_failure` | Catastrophic failure + partial recovery | Mixed |

---

## Fusion Methods

| Method | Description | Best for |
|---|---|---|
| `confidence_weighted` | Quality × freshness × reliability × (optional adversarial down-weight) | Default; handles degraded sensors well |
| `kalman_filter` | Discrete scalar Kalman filter with quality/freshness-derived measurement variance | Strong baseline with temporal smoothing |
| `simple_average` | Unweighted average of all sensors | Baseline |
| `majority_vote` | >50% detected = True | Baseline |
| `best_quality_only` | Trust highest-quality sensor | Baseline |

See `IMPROVEMENTS.md` for the opt-in fusion features added in this fork:
continuous freshness decay, entropy-based weighted disagreement penalty,
residual-based adversarial sensor detection, and ROC/AUC/F1 metrics.
Try them with:

```bash
python run_experiment.py --config config_demo.yaml --compare --scenario stale_data
```

---

## Known Limitations

- **Collusion vulnerability:** Single-sensor spoofing is now mitigated by the optional residual-based adversarial detector (`fusion.adversarial_detection.enabled = true`). However, when **multiple** sensors collude (>= half the network is compromised), the leave-one-out residual check flags the truth-teller. Cross-modality consistency checks are needed to address this — see `FUTURE_IMPROVEMENTS.md` §4.
- **Single-sensor normalisation:** Quality/latency weights only affect the score when multiple sensors are present. Single-sensor detection score is always 0 or 1.
- **Real hardware validation complete:** DJI Mini 2 drone telemetry (69 records, 14/14 timesteps correctly assessed LOW confidence), Canadian Arctic AIS vessel tracking (6 vessels, 213 records, satellite and terrestrial feeds), and live NWS Arctic weather data (Barrow 71°N, Nome, Fairbanks, Cold Bay) validated through the same fusion core.
- **Temporal smoothing only via Kalman baseline:** The default `confidence_weighted` method treats time steps independently. The Kalman baseline now provides a stateful alternative; full multi-target tracking is in `FUTURE_IMPROVEMENTS.md` §5.
- **Small-sample ROC/AUC:** With 5-step scenarios, AUC values are statistically thin. See `FUTURE_IMPROVEMENTS.md` §10.

---

## Running Tests

```bash
python -m pytest tests/ -v
# 133 tests, all passing
```

---

## Requirements

- Python 3.10+
- `pyyaml` — config file parsing
- `requests` — live API adapters (NWS, NOAA, OpenWeather, USGS)
- `anthropic` — LLM operator layer
- `python-dotenv` — API key management
- `pytest` — testing

---

## Status

| Milestone | Status |
|---|---|
| Core fusion logic | Done |
| Reliability memory | Done |
| Confidence engine (configurable) | Done |
| 5 simulated scenarios | Done |
| 3 baseline methods | Done |
| Input validation + error handling | Done |
| Structured logging | Done |
| YAML config file | Done |
| CSV adapter | Done |
| NOAA adapter | Done |
| OpenWeatherMap adapter | Done |
| NWS live Arctic weather adapter | Done |
| USGS live seismic adapter | Done |
| Arctic AIS validation (6 vessels, 213 records) | Done |
| DJI hardware validation (14/14 timesteps) | Done |
| LLM operator layer (claude-sonnet-4-5) | Done |
| 133 unit tests passing | Done |
| Multi-platform live integration | In Progress |
| Operator interface development | Next |

---

*Ananta Meridian Inc. — Defence / Dual-Use Software | TRL 3*

---
