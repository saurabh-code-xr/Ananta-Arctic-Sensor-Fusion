# Ananta Meridian — Technical Architecture
*Generated April 2026*

```
╔══════════════════════════════════════════════════════════════╗
║                    ANANTA MERIDIAN                           ║
║         Confidence-Aware Degraded Sensor Fusion              ║
╚══════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LAYER 1 — INPUT (What comes in)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [DJI Drone]    [Simulated     [NOAA Weather]  [OpenWeather]
  Telemetry      Sensor Arrays]  API             API
      │                │              │               │
      └────────────────┴──────────────┴───────────────┘
                                │
                    Each sensor reports:
                    • detected? (yes/no)
                    • quality (0.0 → 1.0)
                    • latency (milliseconds)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LAYER 2 — PRE-PROCESSING (Clean before fusing)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌─────────────────────┐    ┌──────────────────────────┐
  │   FRESHNESS DECAY   │    │   ADVERSARIAL DETECTOR   │
  │                     │    │                          │
  │ Old data = less     │    │ Leave-one-out check:     │
  │ trust. Uses         │    │ If sensor claims HIGH    │
  │ exponential curve   │    │ quality but all others   │
  │ not bracket steps   │    │ disagree → FLAG it       │
  │                     │    │ (spoofing proxy)         │
  └─────────────────────┘    └──────────────────────────┘
                    │                    │
                    └────────┬───────────┘
                             │

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LAYER 3 — FUSION CORE (The brain)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌──────────────────────────────────────────────────────┐
  │           CONFIDENCE-WEIGHTED FUSION ENGINE          │
  │                                                      │
  │  For each sensor:                                    │
  │  weight = quality × freshness × reliability_history  │
  │                                                      │
  │  Then check:                                         │
  │  • Are sensors AGREEING or DISAGREEING?              │
  │    → Disagreement = penalty applied                  │
  │    → Disagreement = possible EW/spoofing flag        │
  │                                                      │
  │  Output: weighted detection score (0.0 → 1.0)        │
  └──────────────────────────────────────────────────────┘
           │                          │
           │                   ┌──────────────┐
           │                   │ KALMAN FILTER │
           │                   │ BASELINE      │
           │                   │ (comparison   │
           │                   │  benchmark)   │
           │                   └──────────────┘
           │
  ┌─────────────────────┐
  │  RELIABILITY MEMORY │
  │                     │
  │ Remembers how each  │
  │ sensor performed    │
  │ in the past.        │
  │ Bad history = less  │
  │ trust next time     │
  └─────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LAYER 4 — CONFIDENCE ENGINE (What does the score mean?)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌──────────────────────────────────────────────────────┐
  │              CONFIDENCE EVALUATION ENGINE            │
  │                                                      │
  │  score > 0.7  →  HIGH    ✅ Trust the output        │
  │  score > 0.4  →  MEDIUM  ⚠️  Proceed with caution   │
  │  score ≤ 0.4  →  LOW     ❌ Do not act on this      │
  │                                                      │
  │  Also generates REASONS:                             │
  │  "Sensor disagreement detected"                      │
  │  "High latency on DJI_S4"                           │
  │  "Low quality: sensors 1, 2, 3"                     │
  └──────────────────────────────────────────────────────┘
                             │
                    [COMING NEXT]
                    ┌─────────────────────┐
                    │   LLM REASONING     │
                    │   LAYER (Claude API)│
                    │                     │
                    │ Takes confidence    │
                    │ output + reasons    │
                    │ → plain English     │
                    │ operator guidance   │
                    └─────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LAYER 5 — OUTPUT (What the operator sees)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌──────────────────────────────────────────────────────┐
  │                                                      │
  │  CONFIDENCE:  LOW  ❌                                │
  │                                                      │
  │  REASON: Sensor disagreement detected across         │
  │  3 of 5 inputs. Pattern consistent with EW           │
  │  interference or spoofing.                           │
  │                                                      │
  │  ACTION: Do not act on fused output. Seek            │
  │  secondary confirmation before deciding.             │
  │                                                      │
  └──────────────────────────────────────────────────────┘
              │                    │
        [CAF Operator]      [C2 System / ISR]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION EVIDENCE (What proves TRL 3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [5 Simulated       [DJI Mini 2        [112 Unit
   Scenarios]         Real Hardware]     Tests]
   Arctic dropout     69 records         All passing
   Gradual degrade    14 time steps      0.74 seconds
   Spoofing           14/14 LOW ✅
   Stale data
   Full failure

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVA SULA FRAMEWORK MAPPING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Her Layer 1 — Perception AI          →  Our Layer 1+2+3
  Her Layer 5 — Human Decision Support →  Our Layer 4
  Her Layer 6 — Trust & Command Culture→  Our Layer 5 output

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEY FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  data_fusion/fusion_engine.py      — Layer 3 core
  data_fusion/confidence_engine.py  — Layer 4
  data_fusion/reliability_memory.py — Layer 3 memory
  data_fusion/freshness.py          — Layer 2 decay
  data_fusion/adversarial.py        — Layer 2 spoofing detection
  data_fusion/kalman_baseline.py    — Layer 3 benchmark
  data_fusion/disagreement.py       — Layer 3 entropy penalty
  experiments/metrics.py            — ROC/AUC evaluation
  analyze_dji_flight.py             — Real hardware validation
  tests/                            — 112 tests
```
