# Fraud Detection Platform

**FAANG / Stripe / Amex-grade fraud decisioning system** built with FastAPI, PostgreSQL 16, Qdrant, OpenAI embeddings, Anthropic agent reasoning, NetworkX graph traversal, and immutable audit trails.

---

## Architecture

Six-layer design with seven production services:

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
│  29 tables: dimensions, facts, features, scores, decisions,         │
│  labels, cases, audit, graph, governance                            │
├─────────────────────────────────────────────────────────────────────┤
│  Qdrant (vectors)  │  Redis (cache/queues)  │  NetworkX (graph)    │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Layers

| Layer | Purpose | Tables |
|-------|---------|--------|
| A. Dimensions | Customer, account, card, merchant, device, IP | 6 |
| B. Transactions | Authorization events, clearing, lifecycle | 3 |
| C. Feature Store | Online serving + offline training features | 2 |
| D. Scoring | Model registry, scores, rules, decisions | 4 |
| E. Labels | Fraud labels, chargebacks, label snapshots | 3 |
| F. Investigation | Cases, investigator actions | 2 |
| G. Audit | Immutable audit events, agent traces | 2 |
| H. Graph | Entity nodes, edges, cluster scores | 3 |
| I. Governance | Eval metrics, drift metrics, experiments | 3 |

### Services

| # | Service | Responsibility |
|---|---------|---------------|
| 1 | **Ingestion** | Auth events, device telemetry, IP intel, chargebacks |
| 2 | **Features** | Velocity, spend anomaly, behavioral, geo, merchant risk |
| 3 | **Scoring** | Real-time ML + rules → decision in milliseconds |
| 4 | **Graph Intelligence** | Fraud ring detection, cluster expansion, mule patterns |
| 5 | **Investigator Copilot** | AI case analysis, similar-case retrieval, recommendations |
| 6 | **Model Governance** | Registry, drift monitoring, eval harness, experiments |
| 7 | **Dashboard** | Read-only views: transactions, cases, audit, model health |

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
POST /model/register         — Register new model
POST /model/promote          — Approval-gated promotion
POST /model/evaluate         — Run evaluation
POST /model/experiment       — Create A/B experiment
GET  /model/health/{version} — Model health metrics
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

# Evaluation harness tests
pytest tests/evaluation/ -v

# All tests
pytest -v --cov=src
```

---

## Project Structure

```
├── docker-compose.yml
├── docker/Dockerfile
├── requirements.txt
├── alembic.ini
├── scripts/
│   ├── init_schema.sql          # Full DDL (29 tables, indexes, triggers)
│   ├── seed_data.py             # Demo data seeder
│   └── run_eval.py              # Evaluation harness runner
├── src/
│   ├── main.py                  # FastAPI application
│   ├── core/
│   │   ├── config.py            # Settings / environment
│   │   ├── database.py          # Async SQLAlchemy engine
│   │   └── logging.py           # Structured logging
│   ├── models/                  # SQLAlchemy ORM (all 29 tables)
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
│   ├── services/
│   │   ├── ingestion/           # Service 1: Event ingestion
│   │   ├── features/            # Service 2: Feature computation
│   │   ├── scoring/             # Service 3: ML + rules + decisions
│   │   │   ├── service.py
│   │   │   ├── ml_model.py
│   │   │   └── rules_engine.py
│   │   ├── graph/               # Service 4: NetworkX graph intel
│   │   ├── copilot/             # Service 5: AI investigator
│   │   ├── governance/          # Service 6: Model governance
│   │   └── dashboard/           # Service 7: Read-only views
│   ├── evaluation/
│   │   └── harness.py           # Offline eval: AUC, precision, recall, regression
│   ├── api/routes/              # FastAPI route handlers
│   ├── utils/
│   │   └── notifications.py     # Slack integration
│   └── db/migrations/           # Alembic migrations
└── tests/
    ├── unit/
    ├── integration/
    └── evaluation/
```
# Fraud-detection-system
