# 2-4 Week Roadmap: TRL 2 → TRL 3 + ARC Module Alignment

## Goal
Move from TRL 2 (analytical proof-of-concept) to **TRL 3 proof-of-concept with validation evidence** while building ARC programme readiness.

## Critical ARC Modules (Next 2-4 weeks)
1. **Module 4: Technology Readiness & Integration** — TRL progression, testing, validation framework
2. **Module 2: Defence Procurement & Bid Strategy** — Understand RFPs, primes, subcontracting
3. **Module 3: Compliance & Cybersecurity** — Controlled Goods Program basics, CMMC/NIST awareness

---

## Week 1: Foundation & Module 4 Prep

**Focus:** Solidify architecture, establish validation baseline

### Technical Work
- [ ] Audit code structure → identify what needs modularization
- [ ] Document current architecture (what's in each module, why)
- [ ] Create a `tests/` directory structure for unit/integration tests
- [ ] Write README that explains system architecture clearly
- [ ] Define TRL 3 validation criteria for your system

### ARC Module Alignment
- **Module 4 prep:** Start thinking about "what does validation look like for this?"
- Output: Architecture diagram + validation plan sketch

### Deliverable
- Clean, documented codebase ready for testing
- Architecture document (1-2 pages): modules, interfaces, data flow
- Validation strategy outline (what will prove TRL 3 readiness?)

---

## Week 2: Validation & Testing Harness (Module 4 core)

**Focus:** Build repeatable experiments, establish baselines

### Technical Work
- [ ] Create baseline fusion methods:
  - Naive method 1: Simple average of detected sensors
  - Naive method 2: Majority voting
  - Your current method
- [ ] Build experiment runner that:
  - Takes a scenario as input
  - Runs all three fusion methods
  - Logs structured results (JSON/CSV)
  - Computes quantitative metrics (sensitivity, specificity, confidence calibration)
- [ ] Add unit tests for core modules:
  - Test confidence evaluation logic
  - Test reliability update logic
  - Test disagreement penalty
- [ ] Document each scenario: what degradation it models, why it's relevant to defence

### ARC Module Alignment
- **Module 4:** "How would you validate this works?" → You now have repeatable experiments
- **Module 2 prep:** Think about how a prime contractor would want to see this validated

### Deliverable
- Experiment runner that produces structured logs
- Baseline comparison showing where your method outperforms simpler approaches
- Test suite with >70% code coverage on core logic
- Scenario documentation

---

## Week 3: Confidence Calibration & Robustness (TRL 3 validation)

**Focus:** Prove confidence system is trustworthy and failure modes are understood

### Technical Work
- [ ] Add confidence calibration analysis:
  - For each scenario, does HIGH confidence correlate with actual correctness?
  - Do LOW confidence outputs actually fail?
  - Generate calibration curves (confidence vs. actual performance)
- [ ] Test failure modes:
  - All sensors fail → graceful degradation?
  - Sensor disagrees → how does system respond?
  - High-latency data → does confidence degrade appropriately?
  - Stale data → what happens?
- [ ] Document known limits:
  - At what number/quality of sensor failures does the system break?
  - What's the confidence floor? When is it unreliable?
  - What latency thresholds matter?
- [ ] Improve logging → every decision step is traceable

### ARC Module Alignment
- **Module 4:** Confidence calibration is key TRL 3 evidence
- **Module 3 prep:** Auditability matters for compliance

### Deliverable
- Confidence calibration report (confidence vs. actual performance curves)
- Failure mode analysis document
- Test results showing graceful degradation
- Audit trail: can trace any decision back to input data

---

## Week 4: Defence Context & Module 2/3 Alignment

**Focus:** Package your TRL 3 evidence for defence market context

### Technical Work
- [ ] Update code with:
  - Docstrings explaining **why** design choices were made
  - Comments on defence-relevant tradeoffs (e.g., interpretability vs. accuracy)
  - Configuration files for easy scenario/parameter tuning
- [ ] Add compliance-awareness:
  - Document data flows (where does data come from, where does it go?)
  - Explain how system could integrate with defence workflows
  - Note any ITAR/EIPA considerations (if applicable)
- [ ] Create a validation report (2-3 pages):
  - What we built and why
  - Validation evidence (baselines, failure modes, confidence calibration)
  - Known limits and assumptions
  - Recommendations for next stage (TRL 4)

### ARC Module Alignment
- **Module 2 (Defence Procurement):** "How would a defence procurer see this?"
- **Module 3 (Compliance):** Data handling, auditability, integration readiness

### Deliverable
- Clean, well-documented codebase with compliance awareness
- Validation report suitable for defence stakeholder review
- Demo script that shows system under degraded conditions
- Recommendations for TRL 4 work

---

## Success Criteria (TRL 3 Readiness)

By end of Week 4, you should have evidence of:

### Technical Maturity
- ✅ Modular architecture with clear interfaces
- ✅ Repeatable experiments with structured logging
- ✅ Comparison against baselines (showing where your method adds value)
- ✅ Confidence calibration (confidence ≈ actual performance)
- ✅ Documented failure modes and limits
- ✅ >70% test coverage on core logic
- ✅ Traceable decision paths (auditable)

### Defence-Ready Thinking
- ✅ Understand RFP landscape (Module 2 awareness)
- ✅ Know compliance baseline (Module 3 awareness)
- ✅ Can articulate TRL progression (Module 4)
- ✅ System is defensible to a procurer

---

## Outputs to Track

### Weekly
- Code commits with clear messages
- Test results and coverage reports
- Experiment logs (JSON/CSV)

### End of each 2-week phase
- Technical documentation update
- Test results summary
- One-page progress note for ARC programme

### End of Week 4
- **Validation Report** (defence-audience ready)
- **Codebase** (clean, tested, documented)
- **Demo capability** (show system working under degradation)

---

## What NOT to do (avoid wasting time)

❌ Don't optimize for speed/latency yet (post-TRL-3 concern)  
❌ Don't build dashboards or UIs (post-TRL-3 concern)  
❌ Don't integrate with real hardware (post-TRL-4 concern)  
❌ Don't work on commercial models or pricing (post-TRL-3 concern)  
❌ Don't over-engineer the code (clean is enough)  
❌ Don't write long papers (concise validation evidence matters)  

---

## ARC Programme Alignment

### Module 2 (Defence Procurement) 
- Attend sessions on RFPs and subcontracting
- Note: Your validation report is the kind of thing a prime contractor might request
- Understand the market you're entering

### Module 3 (Compliance & Cybersecurity)
- Learn Controlled Goods Program basics
- Understand CMMC/NIST relevance to defence software
- Your code auditability supports compliance readiness

### Module 4 (Technology Readiness)
- Attend sessions on TRL progression
- **Your validation plan directly supports this module**
- Use their frameworks to structure your evidence

---

## Questions to Guide Your Work

**Weeks 1-2:**
- Can someone read my code and understand what it does?
- Are my experiments repeatable?
- Where does my method outperform simpler approaches?

**Weeks 2-3:**
- Is my confidence system calibrated to real performance?
- What breaks the system?
- Can I trace any decision back to input data?

**Week 4:**
- Would a defence procurer trust this system?
- Could a prime contractor integrate this?
- Am I ready for TRL 4 (better realism, more scenarios)?
