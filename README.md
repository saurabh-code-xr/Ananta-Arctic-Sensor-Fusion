# Ananta Meridian — Degraded Sensor Fusion

A software-first, hardware-agnostic, confidence-aware sensor fusion system for degraded environments.

**Current TRL:** 3 (proof of concept validated in simulated degraded sensing scenarios)

---

## What It Does

Combines inputs from multiple sensors operating under degraded conditions and produces a single fused detection output with an operator-facing confidence level (HIGH / MEDIUM / LOW).

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

# Use real NOAA weather data (requires free API token)
python run_experiment.py --source noaa

# Use OpenWeatherMap live data (requires free API key)
python run_experiment.py --source openweather

# Use your own sensor CSV file
python run_experiment.py --source csv --csv-file data/your_sensors.csv
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
  disagreement_penalty: 0.8   # lower = harsher penalty for sensor conflict

  freshness_brackets:
    # Increase max_latency_ms for satellite comms or slow sensor networks
    - max_latency_ms: 500     # was 100 — adjusted for high-latency environment
      factor: 1.0
    ...

confidence:
  thresholds:
    high:
      min_score: 0.8          # raise for conservative HIGH confidence
      max_latency_ms: 200     # lower for fresher-data requirements
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

**Option B: Live API** (NOAA weather stations)

Set your free NOAA token in `config.yaml` or as env var:
```bash
export NOAA_TOKEN=your_token_here
python run_experiment.py --source noaa
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
├── utils.py            # Freshness factor, input validation (shared)
├── fusion_engine.py    # Confidence-weighted fusion core
├── confidence_engine.py# HIGH/MEDIUM/LOW confidence evaluation
├── reliability_memory.py# Per-sensor reliability tracking
├── scenarios.py        # Simulated degraded sensing scenarios (5)
├── baselines.py        # Naive baselines for benchmarking (3)
├── config.py           # Config loader (config.yaml)
├── logger.py           # Logging setup
└── adapters/
    ├── csv_adapter.py      # Pre-recorded sensor logs
    ├── noaa_adapter.py     # NOAA weather station data
    └── openweather_adapter.py # OpenWeatherMap live data

experiments/
└── runner.py           # Repeatable experiment runner + metrics

tests/                  # 65 tests, all passing
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
| `confidence_weighted` | Quality × freshness × reliability weighting | Default; handles degraded sensors well |
| `simple_average` | Unweighted average of all sensors | Baseline |
| `majority_vote` | >50% detected = True | Baseline |
| `best_quality_only` | Trust highest-quality sensor | Baseline |

---

## Known Limitations

- **Spoofing vulnerability:** When compromised sensors report high quality but incorrect detections, the weighting system can be misled (see `conflict_spoofing` scenario results).
- **Single-sensor normalisation:** Quality/latency weights only affect the score when multiple sensors are present. Single-sensor detection score is always 0 or 1.
- **Simulated data only (TRL 3):** Real-world validation with live hardware is the next step (TRL 4).
- **No temporal smoothing:** Each time step is independent. No Kalman filter or state estimation.

---

## Running Tests

```bash
python -m pytest tests/ -v
# 65 tests, all passing
```

---

## Requirements

- Python 3.10+
- `pyyaml` — config file parsing
- `requests` — live API adapters (NOAA, OpenWeather)
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
| 65 unit tests passing | Done |
| Live hardware integration | Next (TRL 4) |
| Real sensor validation | Next (TRL 4) |

---

*Ananta Meridian Inc. — Defence / Dual-Use Software | TRL 3*
