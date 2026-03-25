# Fraud Detection Platform

**FAANG / Stripe / Amex-grade fraud decisioning system** built with FastAPI, PostgreSQL 16, Qdrant, OpenAI embeddings, Anthropic agent reasoning, NetworkX graph traversal, and immutable audit trails.

---

## Architecture

Six-layer design with nine production services:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                          │
├─────────┬──────────┬──────────┬─────────┬──────────┬───────────────┤
│ Service │ Service  │ Service  │ Service │ Service  │ Service       │
│    1    │    2     │    3     │    4    │    5     │  6 & 7        │
│Ingestion│ Features │ Scoring  │  Graph  │ Copilot  │ Governance    │
│         │          │          │  Intel  │          │ & Dashboard   │
├─────────┴──────────┴──────────┴─────────┴──────────┴───────────────┤
│                         PostgreSQL 16                               │
│  28 tables: dimensions, facts, features, scores, decisions,         │
│  labels, cases, audit, graph, governance                            │
├─────────────────────────────────────────────────────────────────────┤
│  Qdrant (vectors)  │  Redis (cache/queues)  │  NetworkX (graph)    │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Layers (28 tables)

| Layer | Purpose | Tables |
|-------|---------|--------|
| A. Dimensions | Customer, account, card, merchant, device, IP, model registry | 7 |
| B. Transactions | Authorization events, clearing, lifecycle | 3 |
| C. Feature Store | Online serving + offline training features | 2 |
| D. Scoring | Model scores, rules, decisions | 3 |
| E. Labels | Fraud labels, label snapshots | 2 |
| F. Investigation | Cases, chargebacks, disputes, case actions, agent traces | 5 |
| G. Audit | Immutable audit events | 1 |
| H. Graph | Entity nodes, edges, cluster scores | 3 |
| I. Governance | Eval metrics, drift metrics, experiments | 3 |

### Services

| # | Service | Responsibility |
|---|---------|---------------|
| 1 | **Ingestion** | Auth events, device telemetry, IP intel, chargebacks |
| 2 | **Features** | Velocity, spend anomaly, behavioral, geo, merchant risk, parity validation |
| 3 | **Scoring** | Real-time ML + rules → decision in milliseconds |
| 4 | **Graph Intelligence** | Fraud ring detection, cluster expansion, mule patterns |
| 5 | **Investigator Copilot** | AI case analysis, similar-case retrieval, recommendations |
| 6 | **Model Governance** | Registry, drift monitoring, eval harness, experiments, model cards |
| 7 | **Dashboard** | Read-only views: transactions, cases, audit, model health |
| 8 | **Economics** | Fraud business metrics, threshold optimization, loss curves |
| 9 | **Replay** | Forensic decision reconstruction, what-if analysis, batch backtesting |

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+

### Run with Docker

```bash
docker-compose up -d
```

Services:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432
- **Qdrant**: localhost:6333
- **Redis**: localhost:6379

### Run locally (development)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start Postgres, Redis, Qdrant via Docker
docker-compose up -d postgres redis qdrant

# Run API
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Seed demo data
python -m scripts.seed_data

# Run evaluation harness
python -m scripts.run_eval
```

---

## API Endpoints

### Real-time Scoring
```
POST /authorize/score        — Score authorization in real-time
```

### Case Management
```
POST /case/create            — Create fraud case
POST /case/review            — Review/disposition a case
GET  /case/{id}/investigate  — AI-assisted investigation
GET  /case/{id}/recommend    — AI-generated action recommendation
```

### Features
```
GET  /features/get/{id}      — Retrieve stored online features
POST /features/compute       — Compute features on demand
POST /features/offline/build — Build offline training features
```

### Graph Intelligence
```
POST /graph/risk             — Compute graph risk for auth
GET  /graph/rings            — Detect fraud rings
GET  /graph/expand/{id}      — Expand cluster from a node
```

### Feedback / Labels
```
POST /feedback/label         — Submit fraud label
POST /feedback/chargeback    — Ingest chargeback
```

### Model Governance
```
POST /model/register         — Register new model (JWT: admin, model_risk)
POST /model/promote          — Approval-gated promotion (JWT: admin)
POST /model/evaluate         — Run evaluation (JWT: admin, model_risk)
POST /model/experiment       — Create A/B experiment (JWT: admin, model_risk)
GET  /model/health/{version} — Model health metrics
```

### Governance (Model Cards & Contracts)
```
GET  /governance/model-card/{version} — Model card (JWT: admin, model_risk, readonly)
GET  /governance/model-cards          — List all model cards
GET  /governance/compare/{a}/{b}      — Compare two models
GET  /governance/contracts            — List data contracts
GET  /governance/contracts/validate/auth-event — Validate sample event
```

### Economics
```
GET  /economics/summary           — Fraud business metrics
GET  /economics/by-segment        — Metrics by segment
POST /economics/threshold-sweep   — Threshold optimization (JWT: admin, model_risk)
GET  /economics/loss-curve        — Loss curve analysis
```

### Replay & Forensics
```
POST /replay/decision/{id}  — Full decision replay (JWT: admin, model_risk, investigator)
POST /replay/compare         — What-if comparison (JWT: admin, model_risk)
POST /replay/batch           — Batch replay for backtesting (JWT: admin, model_risk)
GET  /features/parity/report — Feature parity report
GET  /features/parity/{id}   — Single parity check
GET  /features/registry      — Feature contract/registry
```

### Observability
```
GET  /ops/metrics            — Full metrics dashboard
GET  /ops/metrics/scoring    — Scoring metrics
GET  /ops/metrics/decisions  — Decision distribution
GET  /ops/metrics/rules      — Rule fire rates
GET  /ops/metrics/parity     — Parity metrics
GET  /ops/metrics/api        — API metrics
POST /ops/metrics/reset      — Reset all metrics (JWT: admin)
```

### Dashboard (Read-Only)
```
GET  /dashboard/transaction/{id}  — Full 360° transaction view
GET  /dashboard/transactions      — Search transactions
GET  /dashboard/cases             — Case queue
GET  /dashboard/cases/summary     — Queue summary
GET  /dashboard/models            — Model health dashboard
GET  /dashboard/audit             — Audit trail
GET  /dashboard/traces/{case_id}  — Agent trace viewer
GET  /dashboard/ops/summary       — Leadership KPIs
```

---

## Key Design Decisions

### Point-in-Time Correctness
Online and offline feature tables are separate to prevent training/serving skew and label leakage.

### Prediction ≠ Decision
`fact_model_score` stores what the model predicted; `fact_decision` stores what business action was taken. Separated for auditability and threshold tuning.

### Delayed Truth
Fraud labels arrive days to months after transactions. `fact_fraud_label` tracks label source, confidence, and receipt time. `fact_label_snapshot` captures label state at training-data cutoff for reproducibility.

### Immutable Audit
`audit_event`, `fact_transaction_lifecycle_event`, `fact_case_action`, and `agent_trace` are append-only with database triggers preventing UPDATE/DELETE.

### Graph Intelligence
NetworkX-based entity graph links accounts, devices, IPs, emails, and merchants. Detects fraud rings, synthetic identities, and mule patterns via connected-component analysis and hop-based risk propagation.

### AI Dual-Mode
Claude agent reasoning when API keys are available; deterministic rule-based fallback otherwise. Every agent step is traced to `agent_trace`.

### Approval-Gated Actions
Model promotion, rule changes, and high-impact actions require explicit human sign-off recorded in the audit trail.

---

## Testing

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Resilience / chaos tests
pytest tests/resilience/ -v

# Evaluation harness tests (fast)
pytest tests/evaluation/ -v -m "not slow"

# Adversarial evaluation (slow)
pytest tests/evaluation/ -v -m slow

# All tests with coverage
pytest -v --cov=src --cov-report=term-missing
```

## Load Testing

```bash
# Start Locust web UI (browse to http://localhost:8089)
locust -f tests/load/locustfile.py --host http://localhost:8000

# Headless mode — 100 users, 10 spawn/sec, 2 min run
locust -f tests/load/locustfile.py --host http://localhost:8000 \
  --users 100 --spawn-rate 10 --run-time 2m --headless
```

---

## Project Structure

```
├── .github/workflows/ci.yml    # CI/CD: lint, test, Docker build
├── docker-compose.yml           # Postgres, Redis, Qdrant, API, Celery worker/beat, Flower
├── docker/Dockerfile
├── requirements.txt
├── pyproject.toml               # Project metadata + deps mirror
├── alembic.ini
├── scripts/
│   ├── init_schema.sql          # Full DDL (28 tables, indexes, triggers)
│   ├── seed_data.py             # Demo data seeder
│   ├── run_eval.py              # Evaluation harness runner
│   ├── run_benchmark.py         # Performance benchmark runner
│   ├── run_simulation.py        # Fraud simulation data generator
│   └── demo_walkthrough.py      # 10-section live demo script
├── src/
│   ├── main.py                  # FastAPI application
│   ├── core/
│   │   ├── config.py            # Settings / environment
│   │   ├── database.py          # Async SQLAlchemy engine (Alembic-managed schema)
│   │   └── logging.py           # Structured logging
│   ├── models/                  # SQLAlchemy ORM (all 28 tables)
│   │   ├── dimensions.py
│   │   ├── transactions.py
│   │   ├── features.py
│   │   ├── scoring.py
│   │   ├── labels.py
│   │   ├── investigation.py
│   │   ├── audit.py
│   │   ├── graph.py
│   │   └── governance.py
│   ├── schemas/                 # Pydantic request/response models
│   ├── contracts/               # Data contracts and schema validation
│   ├── services/
│   │   ├── ingestion/           # Service 1: Event ingestion
│   │   ├── features/            # Service 2: Feature computation + parity
│   │   │   ├── service.py
│   │   │   └── parity.py        # Online/offline feature parity validator
│   │   ├── scoring/             # Service 3: ML + rules + decisions
│   │   │   ├── service.py
│   │   │   ├── ml_model.py
│   │   │   ├── rules_engine.py
│   │   │   └── model_trainer.py
│   │   ├── graph/               # Service 4: NetworkX graph intel
│   │   ├── copilot/             # Service 5: AI investigator
│   │   ├── governance/          # Service 6: Model governance + model cards
│   │   ├── dashboard/           # Service 7: Read-only views
│   │   ├── economics/           # Service 8: Fraud economics + threshold optimizer
│   │   ├── replay/              # Service 9: Decision replay + forensics
│   │   └── observability/       # Runtime metrics collection
│   ├── simulation/              # Fraud simulator (7 attack patterns)
│   ├── evaluation/
│   │   ├── harness.py           # Offline eval: AUC, precision, recall, regression
│   │   └── benchmark.py         # Latency & throughput benchmarking
│   ├── api/
│   │   ├── routes/              # FastAPI route handlers (all JWT-protected)
│   │   └── middleware/          # Auth (JWT/RBAC) + rate limiting
│   ├── workers/                 # Celery workers + beat scheduler
│   │   ├── celery_app.py
│   │   ├── tasks.py
│   │   └── scheduler.py
│   ├── utils/
│   │   ├── notifications.py     # Slack integration
│   │   ├── fx_service.py        # Multi-currency FX normalization
│   │   └── github_workflow.py   # GitHub PR workflow automation
│   └── db/migrations/           # Alembic migrations
├── templates/                   # Jinja2 dashboard templates
│   ├── base.html
│   └── dashboard/               # 10 dashboard views
├── tests/
│   ├── unit/                    # Unit tests (rules, graph, simulator, etc.)
│   ├── integration/             # Scoring pipeline integration tests
│   ├── evaluation/              # Eval harness + adversarial validation
│   ├── resilience/              # Chaos/failure-mode tests
│   └── load/                    # Locust load testing
│       └── locustfile.py
└── docs/
    ├── ARCHITECTURE.md
    └── DEMO_SCRIPT.md
```
# Fraud-detection-system
