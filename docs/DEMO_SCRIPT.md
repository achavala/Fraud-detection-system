# Fraud Detection Platform — Demo Script (Talk Track)

A guided walkthrough for presenters running the live demo. Use alongside `python3 scripts/demo_walkthrough.py`.

**Total duration:** 12–15 minutes | **Audience:** Interviews, investors, enterprise demos

---

## Opening

**What to say:**
> "This is our Fraud Detection Platform — an enterprise-grade real-time risk engine that combines six layers: ingestion, dimensions, features, decisions, case management, and governance. I'll walk through each capability in about 12 minutes."

**What to show:** Run the script; the first section will appear.

**Transition:** "Let's start with our fraud simulation engine."

---

## SECTION 1: Fraud Simulation (~2 min)

**What to say:**
> "We have a vectorized fraud simulator that produces realistic, platform-compatible data. It generates 10,000 transactions in under a second, with seven attack patterns: normal spending, card testing, account takeover, friendly fraud, merchant compromise, fraud rings, and synthetic identity."

**What to show:**
- Generated transaction count and generation time
- Fraud distribution by type (normal ~97.5%, fraud types 0.2–0.6% each)
- Class imbalance (legitimate vs fraud)

**Key talking points:**
- Delayed labels (7–120 days) and concept drift are built in
- Graph edges are generated for entity-relationship analysis
- Same schema as production for seamless training and replay

**Expected output:**
```
Generated 9,997 transactions in 0.072s
Graph edges: 29,940
Fraud distribution: normal 97.5%, ato 0.6%, fraud_ring 0.6%, etc.
Class imbalance: Legitimate 97.5%, Fraud 2.5%
```

**Transition:** "We train XGBoost and LightGBM on this data — let's run the training pipeline."

---

## SECTION 2: Model Training (~2 min)

**What to say:**
> "Our model trainer uses the simulator output or synthetic data, trains calibrated XGBoost classifiers, and produces serialized artifacts. We report AUC-ROC, AUC-PR, precision, and recall at a chosen threshold."

**What to show:**
- Training time
- AUC-ROC and AUC-PR
- Precision and recall at p=0.55

**Key talking points:**
- Isotonic calibration for probability estimates
- Champion/shadow deployment for safe rollouts
- Artifacts saved to `models_artifact/` for the scoring service

**Expected output:**
```
Trained XGBoost in ~0.7s
AUC-ROC: high (e.g., 0.95+)
AUC-PR: high
Precision / Recall at p=0.55
```

**Transition:** "Now let's score a transaction in real time."

---

## SECTION 3: Real-Time Scoring (~2 min)

**What to say:**
> "We score two transactions: one suspicious — high velocity, VPN, new device — and one normal. The pipeline uses online features, the rules engine, and the ML model in an ensemble: 70% ML and 30% rules."

**What to show:**
- Suspicious transaction: HIGH risk band, high probability, multiple rules fired
- Normal transaction: LOW risk band, low probability

**Key talking points:**
- Sub-50 ms end-to-end latency in production
- Explainable: every rule that fired is visible
- Risk bands: HIGH (decline/review), MEDIUM (step-up), LOW (approve)

**Expected output:**
```
SUSPICIOUS: ML 0.85+ | Ensemble 0.90+ | Risk band: HIGH
Rules fired: R001, R002, R003, R004, R005, R006, R007
NORMAL: ML ~0.15 | Ensemble ~0.10 | Risk band: LOW
```

**Transition:** "Let's look at which rules fired and why."

---

## SECTION 4: Rules Engine (~1 min)

**What to say:**
> "Our rules engine evaluates eight deterministic rules. For the suspicious transaction, we see exactly which rules fired and their human-readable explanations."

**What to show:**
- List of fired rules with explanations (e.g., "Card used 8 times in 10 minutes", "Transaction originated from VPN/proxy/Tor")

**Key talking points:**
- Versioned rule sets (e.g., rules-v3.1.0)
- Severity levels: high, medium, low
- Rules complement ML — they catch patterns models may miss

**Expected output:**
```
R001 high_velocity_card_10m: Card used 8 times in 10 minutes
R002 multi_account_device_30d: Device linked to 4 accounts in 30 days
R003 vpn_proxy_tor: Transaction originated from VPN/proxy/Tor
...
```

**Transition:** "We also use graph intelligence to detect fraud rings."

---

## SECTION 5: Graph Analysis (~2 min)

**What to say:**
> "We build an entity graph — account, device, IP, card, merchant — and detect fraud rings by finding connected components with shared devices and IPs. We also flag synthetic identity and mule patterns."

**What to show:**
- Graph size (nodes, edges)
- Number of fraud rings detected
- Cluster details: accounts, shared devices, shared IPs, ring score

**Key talking points:**
- networkx-based, production-ready
- Hop-based risk propagation
- Complements ML and rules for organized fraud

**Expected output:**
```
Built graph: 6 nodes, 5 edges
Detected 1 fraud ring(s)
Cluster: 3 accounts, 1 shared devices, 1 shared IPs, ring_score=0.74
```

**Transition:** "Let's run our latency benchmark."

---

## SECTION 6: Benchmark (~2 min)

**What to say:**
> "We benchmark each component and the end-to-end pipeline. Our SLOs are: scoring p99 under 50 ms, model inference under 10 ms, rules under 5 ms, end-to-end under 100 ms. Throughput is over 100,000 requests per second."

**What to show:**
- p50, p95, p99 for each component
- Throughput (req/s) for scoring
- SLO pass/fail for each target

**Key talking points:**
- Production-ready latency
- Heuristic fallback when model artifact is missing
- Automated in CI

**Expected output:**
```
scoring_latency: p99 ~0.02 ms | 117,000+ req/s
model_inference: p99 ~1.5 ms
rules_engine: p99 ~0.01 ms
end_to_end: p99 ~0.1 ms
All SLOs: PASS
```

**Transition:** "We optimize thresholds by business cost, not just ML metrics."

---

## SECTION 7: Threshold Optimization (~2 min)

**What to say:**
> "Our threshold optimizer finds the loss-optimal decision threshold given prevented fraud, missed fraud, false positives, and review costs. We support single-threshold and three-tier: decline, review, step-up."

**What to show:**
- Optimal single threshold and net savings
- Approval rate and FPR
- 3-tier thresholds (decline, review, step_up)

**Key talking points:**
- Business-aware: review cost, FP cost, missed fraud cost
- Constraints: min approval rate, max FPR
- Trade-off exploration via threshold sweep

**Expected output:**
```
Single-threshold optimal: 0.72
Net savings: varies with data
3-tier: decline=0.90, review=0.85, step_up=0.55
```

**Transition:** "Here's how we track economics."

---

## SECTION 8: Economics (~1 min)

**What to say:**
> "We track business decision metrics: prevented fraud dollar volume, missed fraud, false positive volume, business cost, net savings, and fraud basis points."

**What to show:**
- Prevented fraud $, missed fraud $, FP volume $
- Business cost, net savings
- Fraud basis points

**Key talking points:**
- Beyond ML: real business impact
- Basis points for board-level reporting

**Expected output:**
```
Prevented fraud $:  $527.54
Missed fraud $:     $29,841.75
...
Net savings:        $-30,266.68
Fraud basis points: 10.40
```

**Transition:** "We enforce feature parity between online and offline."

---

## SECTION 9: Feature Parity (~1 min)

**What to say:**
> "Our feature registry defines 19 features with types, ranges, and descriptions. The schema checksum ensures contract versioning — if training and serving features diverge, we detect it."

**What to show:**
- Feature count (19)
- Sample features with name, type, description
- Schema checksum

**Key talking points:**
- Training/serving skew detection
- Parity validation in CI
- Point-in-time correctness for offline features

**Expected output:**
```
Feature registry: 19 features
customer_txn_count_1h: int — Customer transactions in last 1 hour
...
Schema checksum: 5365941acd28050b
```

**Transition:** "Let me summarize what we've covered."

---

## SECTION 10: Summary (~1 min)

**What to say:**
> "We've demonstrated: fraud simulation, model training, real-time scoring, the rules engine, graph fraud ring detection, benchmarking, threshold optimization, economics, and feature parity. All capabilities are production-ready and covered by 81+ automated tests."

**What to show:**
- Checklist of demonstrated capabilities
- "All capabilities demonstrated. Demo complete."

**Closing:**
> "Questions? I can go deeper on any layer — architecture, data model, or API."

---

## Quick Reference

| Section | Duration | Focus |
|---------|----------|--------|
| 1 | ~2 min | Fraud simulation, 7 attack patterns |
| 2 | ~2 min | XGBoost training, metrics |
| 3 | ~2 min | Real-time scoring, ensemble |
| 4 | ~1 min | Rules engine, explanations |
| 5 | ~2 min | Graph, fraud rings |
| 6 | ~2 min | Benchmark, SLOs |
| 7 | ~2 min | Threshold optimization |
| 8 | ~1 min | Economics |
| 9 | ~1 min | Feature registry |
| 10 | ~1 min | Summary |

---

## Troubleshooting

- **Script fails on import:** Ensure you run from project root: `python3 scripts/demo_walkthrough.py`
- **Model training slow:** First run fetches/creates model; subsequent runs are faster
- **Benchmark SLO fail:** Check CPU load; benchmarks are sensitive to machine conditions
