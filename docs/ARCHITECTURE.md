# Fraud Detection Platform — Architecture Overview

## Executive Summary

The Fraud Detection Platform is an enterprise-grade, real-time transaction risk engine designed for issuers, acquirers, and fintechs. It combines six architectural layers—event ingestion, dimension management, feature engineering, decision orchestration, case management, and governance—into a single system that delivers sub-50ms scoring, point-in-time correct features, and full forensic replay. Differentiators include graph-based fraud ring detection, calibrated ML ensembles, business-aware threshold optimization, and an AI copilot for investigators backed by vector similarity search.

---

## System Architecture

### High-Level Architecture

#### 1. Event Ingestion Layer

Receives authorization events, clearing events, and chargeback feedback via REST APIs. Supports auth-only and full lifecycle flows. Events are persisted to fact tables with immutable audit triggers and indexed for downstream feature computation and replay.

#### 2. Dimension Management

Maintains consistent entity dimensions used across the pipeline:

- **Customer** — identity, profile, historical behavior
- **Card** — BIN, product, lifecycle
- **Merchant** — MCC, geography, chargeback history
- **Device** — fingerprint, risk signals, account associations
- **IP** — geography, proxy/VPN flags, card clustering
- **Account** — linkage to customer, cards, devices

Dimensions are referenced by IDs; facts store foreign keys for join-free lookups in feature pipelines.

#### 3. Feature Engineering

- **Online (real-time):** Velocity (1h/24h/10m), geo distance, amount anomaly vs customer/merchant p95, device risk, behavioral risk, proxy/VPN flag, graph cluster risk. Computed at decision time with point-in-time correctness.
- **Offline (batch):** Same schema for training; built from historical fact tables and label snapshots with strict temporal cutoffs to avoid leakage.

Feature parity validation compares online vs offline outputs to detect training/serving skew.

#### 4. Decision Engine

- **ML Scoring:** XGBoost (champion) and LightGBM (shadow) with isotonic calibration.
- **Rules Engine:** Versioned deterministic rules (R001–R008) for velocity, device, VPN, amount, rapid-fire patterns.
- **Graph Risk:** networkx-based cluster expansion, fraud ring detection, synthetic identity and mule patterns.
- **Ensemble:** 70% ML + 30% rules with configurable thresholds (decline / review / step-up).

#### 5. Case Management & Investigation

- Fraud cases and chargeback cases tracked in fact tables.
- AI copilot for investigation assistance.
- Qdrant vector store for similar-case retrieval.
- Agent traces for audit and reproducibility.

#### 6. Governance & Auditability

- Model registry for champion/shadow/archived versions.
- Drift monitoring for features and model performance.
- Threshold experiments with A/B-style evaluation.
- Audit events (immutable) for all critical actions.

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| API | FastAPI (async Python, ORJSONResponse) |
| Database | PostgreSQL 16 (29 tables, immutable audit triggers) |
| Cache / Broker | Redis (rate limiting, Celery broker) |
| Vector Store | Qdrant (similar-case retrieval) |
| ML Models | XGBoost, LightGBM (calibrated fraud classifiers) |
| Graph | networkx (entity graph, fraud rings) |
| AI | Anthropic Claude / OpenAI (copilot, embeddings) |
| Background Jobs | Celery (drift, parity, label snapshots) |
| Migrations | Alembic |
| Orchestration | Docker Compose |

---

## Data Model

29 tables grouped by layer:

**Dimensions**

- dim_customer, dim_card, dim_merchant, dim_device, dim_ip, dim_account, dim_model_registry

**Facts — Transactions & Lifecycle**

- fact_authorization_event, fact_clearing_event, fact_transaction_lifecycle_event

**Features**

- fact_transaction_features_online, fact_transaction_features_offline

**Scoring**

- fact_model_score, fact_rule_score, fact_decision

**Investigation**

- fact_fraud_case, fact_chargeback_case, fact_case_action, fact_dispute, agent_trace

**Labels**

- fact_fraud_label, fact_label_snapshot

**Graph**

- graph_entity_node, graph_entity_edge, fact_graph_cluster_score

**Governance**

- fact_model_eval_metric, fact_feature_drift_metric, fact_threshold_experiment

**Audit**

- audit_event

---

## Scoring Flow

1. Auth event received via `POST /authorize/score`.
2. Transaction ingested → `fact_authorization_event`.
3. Online features computed (velocity, geo, amount anomaly, device risk).
4. Rules engine evaluates deterministic rules.
5. ML model scores with XGBoost (champion) + LightGBM (shadow).
6. Graph risk computed via networkx.
7. Ensemble decision: 70% ML + 30% rules.
8. Decision stored → `fact_decision`.
9. If high risk: fraud case created, Slack alert sent.
10. All steps logged to `audit_event`.

---

## Replay & Forensic Reconstruction

For any transaction, the platform reconstructs:

- Original payload and features at decision time
- Model version, scores, rule firings
- Thresholds active at that moment
- What-if analysis with different models/thresholds
- Later-arriving labels and decision correctness

---

## Economics & Threshold Optimization

Business decision metrics beyond ML:

- **Prevented fraud $** — fraud declined or sent to review
- **Missed fraud $** — fraud approved
- **False positive $** — legitimate transactions blocked
- **Manual review cost** — per-review cost
- **Customer friction rate** — step-up/block rate impact
- **Net fraud savings** — prevented fraud minus costs

Threshold sweep evaluates approval rate, FPR, and net savings tradeoffs. Three-tier optimization supports decline / review / step-up bands.

---

## Graph Intelligence

- **Entity relationship graph:** account ↔ device ↔ IP ↔ card ↔ merchant
- **Fraud ring detection** via connected components and shared device/IP patterns
- **Synthetic identity detection** — multiple accounts, few shared identifiers
- **Mule pattern detection** — redistribution across accounts via shared infrastructure
- **Hop-based risk propagation** — blast-radius style scoring from risky neighbors

---

## Resilience & Failure Handling

| Failure Mode | Behavior |
|--------------|----------|
| DB unavailable | 503 with graceful error |
| Qdrant down | Copilot deterministic fallback |
| Slack timeout | 5-second timeout, non-blocking |
| Model artifact missing | Heuristic fallback |
| Expired JWT | 401 rejection |
| Rate limit burst | 429 after limit |

---

## Performance

| Component | p50 | p95 | p99 | SLO | Status |
|-----------|-----|-----|-----|-----|--------|
| Scoring | 0.009 ms | 0.009 ms | 0.025 ms | <50 ms | PASS |
| Model Inference | 0.725 ms | 1.379 ms | 2.054 ms | <10 ms | PASS |
| Rules Engine | 0.003 ms | 0.004 ms | 0.004 ms | <5 ms | PASS |
| End-to-End | 0.035 ms | 0.083 ms | 0.136 ms | <100 ms | PASS |

**Throughput:** 107,024 requests/second

---

## Test Coverage

81+ automated tests across:

- **Unit tests** — rules, model, FX, auth, graph, simulator, threshold, benchmark
- **Integration tests** — full scoring pipeline, model training
- **Resilience tests** — 10 chaos/failure-mode tests
- **Adversarial validation** — attack-pattern blind spots

---

## Fraud Simulator

Realistic simulation engine with seven attack patterns:

- Normal spending (97.5%), card testing, account takeover, friendly fraud
- Merchant compromise, fraud rings, synthetic identity
- Delayed labels (7–120 days), concept drift simulation
- 100,000 transactions generated in 0.56 seconds

---

## Security

- JWT authentication with role-based access control
- Rate limiting per endpoint category
- Immutable audit events (DB trigger enforced)
- GitHub PR workflow for rule/model changes with approval gates
