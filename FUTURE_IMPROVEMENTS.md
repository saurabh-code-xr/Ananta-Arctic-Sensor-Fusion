# Future Improvements

A roadmap of meaningful upgrades beyond what's in `IMPROVEMENTS.md`. These
require larger lifts (research, additional dependencies, real-world data,
or significant rearchitecture) and are out of scope for this PR.

Ranked rough priority for defence-market readiness.

---

## 1. Real Bayesian / probabilistic fusion (algorithmic depth)

**Problem.** The core fusion stays a heuristic: a multiplicative weighting
of self-reported quality, latency, and historical reliability, normalized
into a [0, 1] score. The Kalman baseline added in this branch is a step
toward a proper probabilistic formulation but is still a 1-D scalar filter.

**What to build.**
- **Dempster-Shafer evidence combination** for handling explicit
  uncertainty mass (sensors can express "I don't know") rather than
  forcing every reading into a binary detect/no-detect.
- **Bayesian network** with sensor reliability priors learned from
  historical data instead of bracket tables.
- **Particle filter** for non-Gaussian state distributions (multi-modal
  beliefs about target presence/location).

**Why it matters.** Defence reviewers expect at least one of these
formulations as a baseline. "Confidence-weighted with quality factors"
won't survive a technical due-diligence call with anyone from CMRE,
DSTG, or Lincoln Lab.

---

## 2. Calibrated confidence levels (HIGH/MEDIUM/LOW must mean something)

**Problem.** The HIGH/MEDIUM/LOW labels are produced from hardcoded
thresholds. There's no calibration check that a "HIGH" confidence
detection is correct ~90% of the time, that "MEDIUM" is correct ~70%, etc.

**What to build.**
- Reliability diagrams (calibration plots) on real labeled data.
- Platt scaling or isotonic regression to calibrate the score-to-confidence
  mapping.
- Per-scenario calibration for environment-specific operating profiles.

**Why it matters.** "Operator-trustworthy outputs" is the product's pitch.
Trust requires calibration. If "HIGH" actually means 60% accurate in
practice, that's a critical safety failure for any operational user.

---

## 3. Real hardware validation (TRL 3 → TRL 4)

**Problem.** Self-admitted in the README. Everything is simulated.

**What to build.**
- DJI / Mavic drone adapter (Project_Status.md indicates this is the
  immediate next step — good).
- ROS2 bridge for any real multi-sensor robot platform.
- Field test data from an actual cold-weather sensor deployment
  (even at lab scale — a freezer room with cheap IR / acoustic / RGB
  sensors would be a credible TRL 4 demonstration).
- Collect a labeled dataset of real degraded readings to drive the
  calibration work in (2).

**Why it matters.** TRL 3 → TRL 4 is the gating step before any prime
will take a meeting that goes past polite curiosity.

---

## 4. Adversarial robustness against collusion

**Problem.** The residual-based outlier detection added in this branch
handles single-sensor spoofing but cannot detect collusion (multiple
spoofed sensors agreeing with each other). The conflict_spoofing
scenario directly demonstrates this — when 2 of 3 sensors are
compromised, the LOO residual flags the truth-teller as suspect.

**What to build.**
- **Cross-modality consistency checks**: if RADAR and LIDAR are physically
  observing the same scene, their readings should be correlated in
  predictable ways. Sudden decorrelation is a red flag even if both
  sensors "agree" on a detection.
- **Sensor identity / signature verification**: cryptographic attestation
  that readings come from the claimed device.
- **Outlier detection in the joint (quality, latency, detection) space**
  using e.g. isolation forests on historical patterns.
- **Trust bootstrapping**: weight independent sensor classes (RF, optical,
  acoustic) more than redundant sensors of the same class, since
  collusion across modalities is harder.

**Why it matters.** The whole "Arctic / dual-use" framing implies
adversarial environments. If the system collapses against a 2-of-3
spoofing attack, it's not defence-grade.

---

## 5. Temporal smoothing as a first-class feature

**Problem.** Each time step is currently independent (the Kalman baseline
is the lone exception, and it only tracks a scalar). A real operational
fusion system needs persistent state estimation.

**What to build.**
- Multi-target tracking via JPDA (Joint Probabilistic Data Association)
  or MHT (Multiple Hypothesis Tracking).
- Track lifecycle management (track initialization, confirmation,
  termination).
- Out-of-sequence measurement handling for sensors with variable latency.

**Why it matters.** Operational sensor fusion is tracking, not detection.
Detection alone is a midterm exam answer; tracking is the actual product.

---

## 6. Learned reliability instead of hand-tuned bands

**Problem.** Reliability bands are defined in `config.yaml` as hardcoded
thresholds (e.g. `min_avg: 0.8 → factor: 1.0`). There's no learning loop.
A sensor that systematically performs better than its self-reported
quality won't ever get rewarded with higher trust.

**What to build.**
- Online estimation of per-sensor reliability priors from labeled
  outcomes (when ground truth eventually becomes available — e.g. via
  delayed confirmation from another channel).
- Bayesian updating: `posterior = likelihood * prior` per sensor per step.
- Drift detection: flag sensors whose reliability is changing significantly,
  not just whose absolute reliability is low.

**Why it matters.** Self-tuning systems are the difference between a demo
and an operational capability.

---

## 7. Explainability for the operator UX

**Problem.** The current `confidence_reasons` list is a useful start but
is essentially template strings ("quality below threshold", "high latency
detected"). For operator trust in a high-stakes environment, the system
needs to explain *why* the score moved between time steps.

**What to build.**
- SHAP / LIME-style attribution per sensor per time step: "this sensor's
  high latency reduced your confidence by 0.12 this step."
- Counterfactual explanations: "if Sensor C had reported normally, your
  confidence would have been HIGH."
- Trace logs that an audit / investigation can reconstruct.

**Why it matters.** This is actually the strongest market differentiator
for the product. Most defence sensor fusion is opaque. "Explainable
fusion that operators can audit" is a positioning play that nobody else
is doing well.

---

## 8. Performance + scale

**Problem.** The current implementation is pure Python loops. Fine for
prototyping, useless for any real sensor stream.

**What to build.**
- Vectorize fusion with NumPy (especially when N_sensors >> 3).
- Streaming API instead of per-step list-in / dict-out.
- Async adapters (the current adapters are synchronous `requests` calls
  blocking on each I/O).
- Benchmark on 50–100 simulated sensors at 100 Hz.

**Why it matters.** Real maritime / Arctic sensor networks have dozens
of sensor channels per platform.

---

## 9. Environment-specific scenarios (Arctic-real, not Arctic-flavored)

**Problem.** The current "Arctic" scenarios are generic sensor-degradation
patterns dressed in cold-weather language. Nothing in the simulation
encodes actual Arctic sensor failure modes.

**What to build.**
- Sea-ice radar return models (Rayleigh distribution at low SNR).
- GNSS denial / multipath scenarios near the magnetic pole.
- Comms blackout patterns (Iridium SBD pass cadence, Starlink polar gap).
- Thermal drift models for IR sensors at -40°C.
- Saltwater spray / icing on optical sensors.

**Why it matters.** Without these, the "Arctic" framing is marketing copy.
With them, this becomes a genuinely useful Arctic sensor-fusion testbed
that primes might pay for as a simulation environment alone.

---

## 10. Test data realism

**Problem.** The 5 simulated scenarios each have only 5 time steps and
~3 sensors. ROC/AUC computed on this is statistically meaningless — too
few samples, too little variance.

**What to build.**
- Synthetic data generator parameterized by scenario (target trajectory,
  sensor noise model, failure model) producing 1000+ time steps.
- Monte Carlo runs with multiple random seeds, reporting confidence
  intervals on accuracy / AUC / F1.
- Cross-validation across seeds to detect scenario-specific overfitting.

**Why it matters.** Right now, "100% accuracy" and "60% accuracy" both
mean very little because both are computed on 5 samples.

---

## Operational / market work (not code, but on the critical path)

- **End-to-end demo video.** 60 seconds. Sensor stream → fusion → operator
  display. No primes will read a README.
- **Comparison paper.** "Confidence-Weighted Fusion vs. Kalman vs. Bayesian
  Networks on Synthetic Arctic Scenarios" — even a 4-page tech note with
  honest benchmarks is more credible than current docs.
- **Pre-defined integration recipe** for the most likely first prime
  (CAE, Tessellate, Dominion). Not a generic adapter — a specific, named
  integration showing exactly where the code drops into their stack.

---

*Maintained by the Ananta Meridian fork community. PRs welcome.*
