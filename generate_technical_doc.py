#!/usr/bin/env python3
"""
Generate comprehensive technical documentation PDF for the Fraud Detection Platform.
"""
from fpdf import FPDF
import textwrap


class TechDocPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(100, 100, 100)
            self.cell(0, 6, "Fraud Detection Platform - Technical Architecture & Knowledge Transfer Document", align="C")
            self.ln(4)
            self.set_draw_color(200, 200, 200)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def title_page(self):
        self.add_page()
        self.ln(40)
        self.set_font("Helvetica", "B", 28)
        self.set_text_color(20, 60, 120)
        self.cell(0, 15, "FRAUD DETECTION PLATFORM", align="C")
        self.ln(18)
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(60, 60, 60)
        self.cell(0, 12, "Technical Architecture &", align="C")
        self.ln(14)
        self.cell(0, 12, "Knowledge Transfer Document", align="C")
        self.ln(25)
        self.set_draw_color(20, 60, 120)
        self.set_line_width(1)
        self.line(60, self.get_y(), 150, self.get_y())
        self.ln(20)
        self.set_font("Helvetica", "", 12)
        self.set_text_color(80, 80, 80)
        self.cell(0, 8, "Version 2.0.0 | Production-Grade Platform", align="C")
        self.ln(10)
        self.cell(0, 8, "For Engineering, Trading, and Operations Teams", align="C")
        self.ln(10)
        self.cell(0, 8, "March 2026", align="C")
        self.ln(30)
        self.set_font("Helvetica", "I", 10)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, "CONFIDENTIAL - Internal Distribution Only", align="C")

    def section_title(self, num, title):
        self.add_page()
        self.set_font("Helvetica", "B", 20)
        self.set_text_color(20, 60, 120)
        self.cell(0, 12, f"{num}. {title}")
        self.ln(8)
        self.set_draw_color(20, 60, 120)
        self.set_line_width(0.8)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(8)

    def subsection(self, title):
        self.ln(4)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(40, 80, 140)
        self.cell(0, 10, title)
        self.ln(8)

    def sub_subsection(self, title):
        self.ln(2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(60, 60, 60)
        self.cell(0, 8, title)
        self.ln(6)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                self.ln(3)
                continue
            self.multi_cell(0, 5, stripped)
            self.ln(1)

    def bullet(self, text, indent=10):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        x = self.get_x()
        self.set_x(x + indent)
        self.cell(4, 5, "-")
        self.multi_cell(0, 5, f"  {text}")
        self.ln(1)

    def bold_bullet(self, label, text, indent=10):
        self.set_text_color(40, 40, 40)
        x = self.get_x()
        self.set_x(x + indent)
        self.set_font("Helvetica", "", 10)
        self.cell(4, 5, "-")
        self.set_font("Helvetica", "B", 10)
        self.cell(self.get_string_width(f"  {label}: ") + 2, 5, f"  {label}: ")
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def code_block(self, text):
        self.set_fill_color(245, 245, 245)
        self.set_draw_color(200, 200, 200)
        self.set_font("Courier", "", 8)
        self.set_text_color(30, 30, 30)
        x = self.get_x()
        y = self.get_y()
        lines = text.strip().split("\n")
        line_h = 4.5
        block_h = len(lines) * line_h + 6
        if y + block_h > 270:
            self.add_page()
            y = self.get_y()
        self.rect(12, y, 186, block_h, "DF")
        self.set_xy(15, y + 3)
        for line in lines:
            self.cell(0, line_h, line[:120])
            self.ln(line_h)
        self.ln(4)

    def table_header(self, cols, widths):
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(20, 60, 120)
        self.set_text_color(255, 255, 255)
        for i, col in enumerate(cols):
            self.cell(widths[i], 7, col, border=1, fill=True, align="C")
        self.ln()

    def table_row(self, cols, widths, fill=False):
        self.set_font("Helvetica", "", 8)
        self.set_text_color(40, 40, 40)
        if fill:
            self.set_fill_color(240, 245, 255)
        else:
            self.set_fill_color(255, 255, 255)
        max_h = 6
        for i, col in enumerate(cols):
            self.cell(widths[i], max_h, str(col)[:50], border=1, fill=fill)
        self.ln()

    def info_box(self, title, text):
        self.set_fill_color(230, 240, 255)
        self.set_draw_color(20, 60, 120)
        y = self.get_y()
        lines = text.strip().split("\n")
        box_h = len(lines) * 5 + 14
        if y + box_h > 270:
            self.add_page()
            y = self.get_y()
        self.rect(12, y, 186, box_h, "DF")
        self.set_xy(15, y + 3)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(20, 60, 120)
        self.cell(0, 6, title)
        self.ln(6)
        self.set_x(15)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(40, 40, 40)
        for line in lines:
            self.set_x(15)
            self.cell(0, 5, line.strip())
            self.ln(5)
        self.set_y(y + box_h + 4)


def build_document():
    pdf = TechDocPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ==================== TITLE PAGE ====================
    pdf.title_page()

    # ==================== TABLE OF CONTENTS ====================
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(20, 60, 120)
    pdf.cell(0, 12, "TABLE OF CONTENTS")
    pdf.ln(12)

    toc_items = [
        ("1", "Executive Summary & System Overview"),
        ("2", "Container & Pod Architecture (Docker Deployment)"),
        ("3", "Database Schema - 28 Tables (Star Schema)"),
        ("4", "Service Architecture - 9 Production Engines"),
        ("5", "Real-Time Authorization Scoring Call Flow"),
        ("6", "Feature Computation Engine - 19 Features"),
        ("7", "Rules Engine - 8 Deterministic Rules"),
        ("8", "ML Model Scoring Engine (XGBoost / LightGBM)"),
        ("9", "Graph Intelligence Engine - Fraud Ring Detection"),
        ("10", "AI Investigator Copilot (Claude + Qdrant)"),
        ("11", "Decision Replay & What-If Engine"),
        ("12", "Fraud Economics Engine - Trading Standpoint"),
        ("13", "Model Governance & Lifecycle"),
        ("14", "Background Workers (Celery)"),
        ("15", "API Endpoint Reference (44 Endpoints)"),
        ("16", "Observability, Monitoring & Telemetry"),
        ("17", "CI/CD Pipeline & Testing"),
        ("18", "Security: Auth, RBAC, Rate Limiting"),
        ("19", "Call Flow Diagrams (Within & Across Engines)"),
        ("20", "Trading Desk Reference Guide"),
    ]
    for num, title in toc_items:
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(40, 40, 40)
        dots = "." * (70 - len(f"{num}  {title}"))
        pdf.cell(0, 7, f"  {num}.  {title}  {dots}")
        pdf.ln(7)

    # ==================== SECTION 1: EXECUTIVE SUMMARY ====================
    pdf.section_title("1", "Executive Summary & System Overview")

    pdf.body_text(
        "The Fraud Detection Platform is a production-grade, real-time transaction fraud scoring system "
        "built on FastAPI (async Python). It processes card authorization requests in milliseconds, combining "
        "deterministic rules, gradient-boosted ML models (XGBoost/LightGBM), graph-based fraud ring detection, "
        "and AI-powered investigation using Anthropic Claude.\n\n"
        "The platform is designed for financial institutions processing card-present and card-not-present "
        "transactions across multiple channels (POS, eCommerce, ATM, contactless). It covers the full "
        "fraud lifecycle: real-time decisioning, case management, label collection, model retraining, "
        "threshold optimization, and regulatory audit trails."
    )

    pdf.subsection("Key Metrics & SLOs")
    pdf.bold_bullet("Scoring Latency (p99)", "< 500ms end-to-end for full pipeline")
    pdf.bold_bullet("Rules Engine Latency (p99)", "< 50ms for all 8 rules")
    pdf.bold_bullet("Scoring Throughput", "5,000 requests/second (rate-limited)")
    pdf.bold_bullet("Feature Vector", "19 features computed in real-time")
    pdf.bold_bullet("Database Schema", "28 tables in star schema (7 dimension + 21 fact)")
    pdf.bold_bullet("API Surface", "44 REST endpoints across 12 route modules")
    pdf.bold_bullet("Test Coverage", "17 test suites (unit, integration, chaos, load, adversarial)")

    pdf.subsection("Technology Stack")
    widths = [45, 70, 75]
    pdf.table_header(["Layer", "Technology", "Purpose"], widths)
    rows = [
        ("API Framework", "FastAPI + ORJSONResponse", "Async HTTP, auto-docs, high perf JSON"),
        ("Database", "PostgreSQL 16 (asyncpg)", "Primary RDBMS, 28 tables, star schema"),
        ("Cache / Broker", "Redis 7", "Session cache, Celery message broker"),
        ("Vector Store", "Qdrant", "Similar-case retrieval, embeddings"),
        ("ML Models", "XGBoost, LightGBM, scikit-learn", "Champion/shadow fraud scoring"),
        ("Graph Engine", "NetworkX", "Fraud ring detection, hop traversal"),
        ("AI Reasoning", "Anthropic Claude", "Case investigation, risk analysis"),
        ("Embeddings", "OpenAI text-embedding-3-small", "1536-dim vectors for case similarity"),
        ("Background Jobs", "Celery (4 workers)", "Feature backfill, drift, experiments"),
        ("Observability", "OpenTelemetry + Prometheus", "Distributed tracing, metrics"),
        ("Logging", "structlog 24.1", "Structured JSON logging"),
        ("Migrations", "Alembic", "Schema versioning, DDL management"),
        ("Testing", "pytest + Locust", "Unit/integration/load testing"),
        ("CI/CD", "GitHub Actions", "Lint, test, Docker build"),
        ("Container", "Docker + docker-compose", "7 service orchestration"),
    ]
    for i, r in enumerate(rows):
        pdf.table_row(r, widths, fill=(i % 2 == 0))

    # ==================== SECTION 2: CONTAINER ARCHITECTURE ====================
    pdf.section_title("2", "Container & Pod Architecture")

    pdf.body_text(
        "The platform runs as 7 containerized services orchestrated via docker-compose. "
        "In a Kubernetes deployment, each service maps to a separate Pod with its own scaling policy."
    )

    pdf.subsection("Container / Pod Definitions")

    # Pod 1
    pdf.sub_subsection("Pod 1: PostgreSQL 16 (postgres)")
    pdf.bold_bullet("Image", "postgres:16-alpine")
    pdf.bold_bullet("Port", "5432")
    pdf.bold_bullet("Credentials", "fraud_user / fraud_pass / fraud_db")
    pdf.bold_bullet("Volumes", "postgres_data (persistent), init_schema.sql (initialization)")
    pdf.bold_bullet("Health Check", "pg_isready -U fraud_user -d fraud_db (5s interval, 10 retries)")
    pdf.bold_bullet("K8s Equivalent", "StatefulSet with PVC for data persistence")
    pdf.body_text("This is the primary data store. On startup, scripts/init_schema.sql creates all 28 tables, "
                   "indexes, and triggers. The schema uses a star-schema pattern with dimension and fact tables.")

    # Pod 2
    pdf.sub_subsection("Pod 2: Redis 7 (redis)")
    pdf.bold_bullet("Image", "redis:7-alpine")
    pdf.bold_bullet("Port", "6379")
    pdf.bold_bullet("Health Check", "redis-cli ping (5s interval, 5 retries)")
    pdf.bold_bullet("K8s Equivalent", "Deployment (stateless) or StatefulSet with AOF persistence")
    pdf.body_text("Serves dual purpose: (1) Feature cache with 300s TTL for hot features, "
                   "(2) Celery message broker for background task queues (features, labels, governance, experiments).")

    # Pod 3
    pdf.sub_subsection("Pod 3: Qdrant Vector Database (qdrant)")
    pdf.bold_bullet("Image", "qdrant/qdrant:latest")
    pdf.bold_bullet("Ports", "6333 (HTTP API), 6334 (gRPC)")
    pdf.bold_bullet("Volumes", "qdrant_data (persistent)")
    pdf.bold_bullet("Collections", "fraud_case_memory, merchant_attack_patterns, investigator_notes")
    pdf.bold_bullet("Health Check", "curl /healthz (5s interval, 5 retries)")
    pdf.body_text("Stores 1536-dimensional OpenAI embeddings for similar-case retrieval. "
                   "The AI Copilot queries this for context during case investigation.")

    # Pod 4
    pdf.sub_subsection("Pod 4: API Server (api) - PRIMARY APPLICATION")
    pdf.bold_bullet("Build", "docker/Dockerfile (python:3.12-slim base)")
    pdf.bold_bullet("Port", "8000")
    pdf.bold_bullet("Workers", "4 uvicorn workers (--workers 4)")
    pdf.bold_bullet("Dependencies", "postgres (healthy), redis (healthy), qdrant (healthy)")
    pdf.bold_bullet("Health Check", "curl /health (10s interval, 5 retries)")
    pdf.bold_bullet("Volumes", "src/ mounted for live code reload (dev mode)")
    pdf.body_text(
        "The main FastAPI application. Handles all 44 API endpoints. Each request goes through: "
        "CORS middleware -> Rate limiting -> JWT auth -> Route handler -> Service layer -> Database. "
        "This is the pod that traders and upstream systems interact with."
    )

    # Pod 5
    pdf.sub_subsection("Pod 5: Celery Worker (celery-worker)")
    pdf.bold_bullet("Command", "celery -A src.workers.celery_app worker --concurrency=4")
    pdf.bold_bullet("Queues", "features, labels, governance, experiments, celery (default)")
    pdf.bold_bullet("Dependencies", "postgres (healthy), redis (healthy)")
    pdf.bold_bullet("Restart Policy", "unless-stopped")
    pdf.body_text(
        "Runs 4 background task functions: backfill_offline_features, generate_label_snapshots, "
        "compute_drift_metrics, and run_shadow_experiment. Uses SYNCHRONOUS psycopg2 driver "
        "(not asyncpg) since Celery workers are sync. Pool size: 5, max overflow: 5."
    )

    # Pod 6
    pdf.sub_subsection("Pod 6: Celery Beat Scheduler (celery-beat)")
    pdf.bold_bullet("Command", "celery -A src.workers.celery_app beat")
    pdf.bold_bullet("Schedule File", "/tmp/celerybeat-schedule (persistent)")
    pdf.bold_bullet("Dependencies", "redis (healthy)")
    pdf.body_text("Triggers scheduled background tasks on cron intervals: daily label snapshots, "
                   "daily drift metric computation, periodic shadow experiments.")

    # Pod 7
    pdf.sub_subsection("Pod 7: Flower - Celery Monitoring UI (flower)")
    pdf.bold_bullet("Image", "mher/flower:2.0")
    pdf.bold_bullet("Port", "5555")
    pdf.bold_bullet("Broker", "redis://redis:6379/0")
    pdf.body_text("Web dashboard for monitoring Celery worker health, task queues, success/failure rates, "
                   "and task execution history. Used by operations teams.")

    pdf.subsection("Environment Variables (Shared Across Pods)")
    env_vars = [
        ("DATABASE_URL", "postgresql+asyncpg://fraud_user:fraud_pass@postgres:5432/fraud_db"),
        ("DATABASE_URL_SYNC", "postgresql://fraud_user:fraud_pass@postgres:5432/fraud_db"),
        ("REDIS_URL", "redis://redis:6379/0"),
        ("CELERY_BROKER_URL", "redis://redis:6379/0"),
        ("QDRANT_HOST / QDRANT_PORT", "qdrant / 6333"),
        ("ANTHROPIC_API_KEY", "Claude API key for AI investigation"),
        ("OPENAI_API_KEY", "OpenAI key for embeddings (text-embedding-3-small)"),
        ("CHAMPION_MODEL_VERSION", "xgb-v4.2.0 (current production model)"),
        ("SHADOW_MODEL_VERSIONS", "lgb-v5.0.0-rc1 (challenger in shadow mode)"),
        ("SCORE_THRESHOLD_DECLINE", "0.85 (auto-decline threshold)"),
        ("SCORE_THRESHOLD_REVIEW", "0.55 (manual review threshold)"),
        ("SCORE_THRESHOLD_STEPUP", "0.35 (step-up auth threshold)"),
        ("RATE_LIMIT_SCORING_RPS", "5000 (scoring endpoint rate limit)"),
        ("OTEL_SERVICE_NAME", "fraud-detection-platform"),
        ("PROMETHEUS_PORT", "9464 (metrics scrape port)"),
    ]
    w = [70, 120]
    pdf.table_header(["Variable", "Value / Description"], w)
    for i, (k, v) in enumerate(env_vars):
        pdf.table_row((k, v), w, fill=(i % 2 == 0))

    # ==================== SECTION 3: DATABASE SCHEMA ====================
    pdf.section_title("3", "Database Schema - 28 Tables (Star Schema)")

    pdf.body_text(
        "The database follows a star-schema design with 7 dimension tables and 21 fact tables. "
        "All schema is managed via Alembic migrations (src/db/migrations/) and the init_schema.sql "
        "DDL script. The schema is initialized on first Postgres container startup."
    )

    pdf.subsection("Dimension Tables (7)")
    dim_tables = [
        ("dim_customer", "customer_id, name, email, home_country_code, home_region, created_at"),
        ("dim_card", "card_id, customer_id, card_type, issuer, expiry, status"),
        ("dim_merchant", "merchant_id, merchant_name, mcc, country_code, risk_category"),
        ("dim_device", "device_id, device_type, os, browser, emulator_flag, rooted_jailbroken_flag"),
        ("dim_ip", "ip_address, geo_country_code, geo_city, geo_region, isp, proxy_vpn_tor_flag, ip_risk_score"),
        ("dim_account", "account_id, customer_id, account_type, status, opened_at"),
        ("dim_model_registry", "model_version, model_family, model_type, deployment_status, thresholds, owner"),
    ]
    w = [45, 145]
    pdf.table_header(["Table", "Key Columns"], w)
    for i, (t, c) in enumerate(dim_tables):
        pdf.table_row((t, c), w, fill=(i % 2 == 0))

    pdf.subsection("Fact Tables (21)")
    fact_tables = [
        ("fact_authorization_event", "Transaction auth: amount, channel, merchant, device, IP, status"),
        ("fact_clearing_event", "Settlement/clearing records after authorization"),
        ("fact_transaction_lifecycle", "Event timeline: auth_received, features_built, rules_scored, etc."),
        ("fact_transaction_features_online", "19 real-time features for each scored transaction"),
        ("fact_transaction_features_offline", "Training features rebuilt from warehouse (no leakage)"),
        ("fact_model_score", "ML probability, risk band, reason codes, SHAP values, latency"),
        ("fact_rule_score", "Rule evaluation: fired_flag, severity, contribution, explanation"),
        ("fact_decision", "Final decision: approve/decline/review/step_up, scores, source"),
        ("fact_fraud_label", "Ground truth: is_fraud, label_source, confidence, category"),
        ("fact_chargeback_case", "Chargeback records: reason_code, amount, representment_flag"),
        ("fact_label_snapshot", "Point-in-time label snapshots for training datasets"),
        ("fact_fraud_case", "Investigation case: status, queue, priority, assigned_to"),
        ("fact_case_action", "Case actions: review, escalate, close (actor + timestamp)"),
        ("fact_dispute", "Dispute records linked to transactions"),
        ("audit_event", "Immutable audit trail: entity_type, event_type, payload_json"),
        ("agent_trace", "AI copilot traces: step_type, input/output, model_name, latency"),
        ("graph_entity_node", "Graph node: node_id, node_type, entity_ref, risk_score"),
        ("graph_entity_edge", "Graph edge: src_node_id, dst_node_id, edge_type, weight"),
        ("fact_graph_cluster_score", "Cluster risk: size, risky_neighbor_count, synthetic_flag"),
        ("fact_feature_drift_metric", "Feature PSI, null_rate, train_mean vs prod_mean"),
        ("fact_threshold_experiment", "A/B experiment results: champion vs challenger metrics"),
    ]
    w = [55, 135]
    pdf.table_header(["Table", "Description"], w)
    for i, (t, c) in enumerate(fact_tables):
        pdf.table_row((t, c), w, fill=(i % 2 == 0))

    # ==================== SECTION 4: SERVICE ARCHITECTURE ====================
    pdf.section_title("4", "Service Architecture - 9 Production Engines")

    pdf.body_text(
        "The platform is organized into 9 production service engines, each responsible for a distinct "
        "domain. All services are initialized per-request with a database session and communicate "
        "through shared database state. There are no inter-service HTTP calls - all engines run "
        "in the same process and share the same async event loop within the API pod."
    )

    pdf.subsection("Service Map")
    svc_data = [
        ("1", "IngestionService", "src/services/ingestion/service.py", "Event, label, chargeback ingestion"),
        ("2", "FeatureService", "src/services/features/service.py", "19-feature online + offline computation"),
        ("3", "ScoringService", "src/services/scoring/service.py", "Orchestrator: features + rules + ML + decision"),
        ("3a", "RulesEngine", "src/services/scoring/rules_engine.py", "8 deterministic rules (R001-R008)"),
        ("3b", "FraudModelScorer", "src/services/scoring/ml_model.py", "XGBoost/LightGBM inference + SHAP"),
        ("3c", "ModelTrainer", "src/services/scoring/model_trainer.py", "Training pipeline for new models"),
        ("4", "FraudGraphService", "src/services/graph/service.py", "NetworkX graph, ring detection, risk"),
        ("5", "InvestigatorCopilot", "src/services/copilot/service.py", "AI investigation (Claude + Qdrant)"),
        ("6", "ModelGovernanceService", "src/services/governance/service.py", "Registry, promotion, evaluation"),
        ("7", "DashboardService", "src/services/dashboard/service.py", "Read-only views and aggregations"),
        ("8", "FraudEconomicsService", "src/services/economics/service.py", "Business metrics and threshold sweep"),
        ("9", "DecisionReplayService", "src/services/replay/service.py", "Decision forensics and what-if"),
    ]
    w = [10, 42, 70, 68]
    pdf.table_header(["#", "Service", "File", "Responsibility"], w)
    for i, r in enumerate(svc_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Inter-Engine Communication Pattern")
    pdf.body_text(
        "CRITICAL: All engines run in the SAME PROCESS (API pod). There are NO inter-service HTTP calls. "
        "Communication happens via:\n\n"
        "1. Direct Python method calls (ScoringService calls FeatureService.compute_online_features)\n"
        "2. Shared database state (one engine writes, another reads via SQL queries)\n"
        "3. Celery task queues (API pod enqueues, Worker pod dequeues and processes)\n\n"
        "This means when you see 'Service A calls Service B', it is an in-process Python method call "
        "that executes within the same database transaction and async event loop."
    )

    # ==================== SECTION 5: REAL-TIME SCORING CALL FLOW ====================
    pdf.section_title("5", "Real-Time Authorization Scoring Call Flow")

    pdf.body_text(
        "This is the PRIMARY call flow - what happens when a transaction authorization request "
        "arrives at POST /authorize/score. This is the hot path that traders and payment systems interact with."
    )

    pdf.subsection("End-to-End Flow (Within Single Engine Orchestration)")

    pdf.info_box("CALL FLOW: POST /authorize/score", """
Step 1:  Upstream System --> API Pod (FastAPI) --> CORS --> RateLimit --> JWT Auth
Step 2:  authorize.py route handler validates role (admin/model_risk)
Step 3:  ScoringService(db) instantiated with async DB session
Step 4:  ScoringService.score_authorization(request) begins orchestration
Step 5:    |-- Ingest: Create FactAuthorizationEvent record --> DB (flush)
Step 6:    |-- Lifecycle: Record "auth_received" event
Step 7:    |-- [CALL TO FEATURE ENGINE] FeatureService.compute_online_features()
Step 8:    |     |-- 6 parallel DB queries for velocity/amount/geo/time/device/IP
Step 9:    |     |-- Writes FactTransactionFeaturesOnline --> DB
Step 10:   |-- Lifecycle: Record "features_built" event
Step 11:   |-- Convert features to scoring vector (19 floats)
Step 12:   |-- [CALL TO RULES ENGINE] RulesEngine.evaluate(features)
Step 13:   |     |-- Evaluate 8 rules (R001-R008) against feature vector
Step 14:   |     |-- Write 8 FactRuleScore records --> DB
Step 15:   |     |-- Return fired rules + aggregate score
Step 16:   |-- Lifecycle: Record "rules_scored" event
Step 17:   |-- [CALL TO ML ENGINE] FraudModelScorer.score(features)
Step 18:   |     |-- Load model artifact from disk cache (models_artifact/)
Step 19:   |     |-- If artifact exists: XGBoost/LightGBM predict_proba()
Step 20:   |     |-- If no artifact: calibrated heuristic fallback
Step 21:   |     |-- Write FactModelScore --> DB (champion score)
Step 22:   |-- [CALL TO ML ENGINE] FraudModelScorer.score_shadow(features)
Step 23:   |     |-- Score with shadow models (logged, NOT acted upon)
Step 24:   |     |-- Write FactModelScore --> DB (shadow=True)
Step 25:   |-- Lifecycle: Record "model_scored" event
Step 26:   |-- BLEND SCORES: final = 0.7 * ML_score + 0.3 * rule_score
Step 27:   |-- MAKE DECISION based on thresholds:
Step 28:   |     |-- >= 0.85 --> HARD_DECLINE
Step 29:   |     |-- >= 0.55 (or high-severity rule fired) --> MANUAL_REVIEW
Step 30:   |     |-- >= 0.35 --> STEP_UP (OTP challenge)
Step 31:   |     |-- < 0.35  --> APPROVE
Step 32:   |-- If MANUAL_REVIEW: Create FactFraudCase (auto-routed to queue)
Step 33:   |-- Write FactDecision --> DB
Step 34:   |-- Update auth_event.auth_status (approved/declined/review/challenged)
Step 35:   |-- Write AuditEvent --> DB (immutable trail)
Step 36:   |-- Lifecycle: Record decision event
Step 37:   |-- Calculate total_latency_ms
Step 38: Return AuthorizationResponse to upstream system
""")

    pdf.subsection("Score Blending Formula")
    pdf.code_block("""final_score = 0.7 * model_calibrated_probability + 0.3 * rule_aggregate_score

Rule aggregate scoring (weighted by severity):
  high   severity rule fire: +0.30
  medium severity rule fire: +0.15
  low    severity rule fire: +0.05
  Total capped at 1.0""")

    pdf.subsection("Decision Thresholds (Configurable via Environment)")
    pdf.code_block("""SCORE_THRESHOLD_DECLINE  = 0.85  (auto hard-decline)
SCORE_THRESHOLD_REVIEW   = 0.55  (route to manual review queue)
SCORE_THRESHOLD_STEPUP   = 0.35  (trigger step-up authentication, e.g., OTP)
Below 0.35               = APPROVE

Exception: If ANY high-severity rule fires, force MANUAL_REVIEW regardless of score.""")

    pdf.subsection("Case Auto-Routing (on MANUAL_REVIEW)")
    pdf.code_block("""Queue assignment by score:
  score >= 0.80  -->  high_risk queue,   priority: critical
  score >= 0.60  -->  medium_risk queue, priority: high
  score <  0.60  -->  general queue,     priority: medium""")

    # ==================== SECTION 6: FEATURE ENGINE ====================
    pdf.section_title("6", "Feature Computation Engine - 19 Features")

    pdf.body_text(
        "The Feature Engine computes 19 real-time features for every authorization event. "
        "Features are grouped into 6 categories: velocity, amount anomaly, geo-distance, "
        "time-gap, device risk, and IP intelligence. All features are computed via SQL aggregations "
        "against the fact_authorization_event table."
    )

    pdf.subsection("Complete Feature Vector (19 Features)")
    feat_data = [
        ("1", "customer_txn_count_1h", "Velocity", "COUNT(*) for customer in last 1 hour"),
        ("2", "customer_txn_count_24h", "Velocity", "COUNT(*) for customer in last 24 hours"),
        ("3", "customer_spend_24h", "Velocity", "SUM(billing_amount_usd) customer last 24h"),
        ("4", "card_txn_count_10m", "Velocity", "COUNT(*) for card_id in last 10 minutes"),
        ("5", "merchant_txn_count_10m", "Velocity", "COUNT(*) for merchant in last 10 minutes"),
        ("6", "merchant_chargeback_rate_30d", "Velocity", "chargebacks / total txns for merchant (30d)"),
        ("7", "device_txn_count_1d", "Velocity", "COUNT(*) for device in last 1 day"),
        ("8", "device_account_count_30d", "Velocity", "COUNT(DISTINCT account_id) per device (30d)"),
        ("9", "ip_account_count_7d", "IP Intel", "COUNT(DISTINCT account_id) per IP (7 days)"),
        ("10", "ip_card_count_7d", "IP Intel", "COUNT(DISTINCT card_id) per IP (7 days)"),
        ("11", "geo_distance_from_home_km", "Geo", "Haversine distance: IP location vs home"),
        ("12", "geo_distance_from_last_txn_km", "Geo", "Haversine: current IP vs previous txn IP"),
        ("13", "seconds_since_last_txn", "Time", "Seconds since customer's last transaction"),
        ("14", "amount_vs_customer_p95_ratio", "Amount", "auth_amount / P95(customer amounts, 90d)"),
        ("15", "amount_vs_merchant_p95_ratio", "Amount", "auth_amount / P95(merchant amounts, 90d)"),
        ("16", "proxy_vpn_tor_flag", "IP Intel", "Boolean: dim_ip.proxy_vpn_tor_flag"),
        ("17", "device_risk_score", "Device", "0.4 if emulator + 0.3 if rooted (max 1.0)"),
        ("18", "behavioral_risk_score", "Behavioral", "Reserved for behavioral biometrics (default 0)"),
        ("19", "graph_cluster_risk_score", "Graph", "From graph engine cluster analysis (default 0)"),
    ]
    w = [8, 52, 18, 112]
    pdf.table_header(["#", "Feature", "Category", "Computation"], w)
    for i, r in enumerate(feat_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Feature Computation SQL Pattern")
    pdf.body_text(
        "Each velocity feature follows the same pattern: COUNT or SUM with a time window filter "
        "against fact_authorization_event. For example, card_txn_count_10m executes:\n"
    )
    pdf.code_block("""SELECT COUNT(*)
FROM fact_authorization_event
WHERE card_id = :card_id
  AND event_time >= (NOW() - INTERVAL '10 minutes')""")

    pdf.body_text(
        "Amount ratio features use percentile_cont(0.95) over 90-day windows. "
        "Geo features use the Haversine formula to compute great-circle distance between "
        "IP geolocation (from dim_ip) and customer home location (from dim_customer)."
    )

    # ==================== SECTION 7: RULES ENGINE ====================
    pdf.section_title("7", "Rules Engine - 8 Deterministic Rules")

    pdf.body_text(
        "The Rules Engine runs 8 deterministic rules in parallel with the ML model. "
        "Rules provide interpretable signals and regulatory explanations. "
        "Each rule has an ID, name, severity (high/medium/low), and human-readable explanation. "
        "Rule version: rules-v3.1.0."
    )

    pdf.subsection("Rule Definitions")
    rule_data = [
        ("R001", "high_velocity_card_10m", "HIGH", "card_txn_count_10m >= 5", "Card used N times in 10 min"),
        ("R002", "multi_account_device_30d", "HIGH", "device_account_count_30d >= 3", "Device on N accounts"),
        ("R003", "vpn_proxy_tor", "MEDIUM", "proxy_vpn_tor_flag = True", "VPN/Proxy/Tor detected"),
        ("R004", "amount_exceeds_3x_p95", "MEDIUM", "amount_vs_customer_p95 > 3.0", "Amount Nx customer P95"),
        ("R005", "multi_card_ip_7d", "HIGH", "ip_card_count_7d >= 5", "IP used with N cards in 7d"),
        ("R006", "rapid_fire_under_30s", "HIGH", "seconds_since_last_txn < 30", "Ns since last transaction"),
        ("R007", "emulator_rooted_device", "MEDIUM", "device_risk_score >= 0.4", "Device risk score N"),
        ("R008", "high_spend_24h", "LOW", "customer_spend_24h > 5000", "Customer spent $N in 24h"),
    ]
    w = [12, 45, 18, 55, 60]
    pdf.table_header(["ID", "Name", "Severity", "Condition", "Explanation Pattern"], w)
    for i, r in enumerate(rule_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Aggregate Rule Score Computation")
    pdf.code_block("""severity_weights = {"high": 0.30, "medium": 0.15, "low": 0.05}
aggregate_score = SUM(weight for each fired rule)
aggregate_score = MIN(aggregate_score, 1.0)  # capped at 1.0

Examples:
  - No rules fire:           aggregate = 0.00
  - R003 (medium) fires:     aggregate = 0.15
  - R001 + R006 (both high): aggregate = 0.60
  - R001 + R002 + R005 + R006 (all high): aggregate = 1.00 (capped)""")

    # ==================== SECTION 8: ML MODEL ENGINE ====================
    pdf.section_title("8", "ML Model Scoring Engine")

    pdf.body_text(
        "The ML engine supports XGBoost and LightGBM models loaded from serialized .pkl artifacts. "
        "It runs champion + shadow scoring, generates SHAP explanations, and falls back to a "
        "calibrated heuristic when no model artifact is available."
    )

    pdf.subsection("Model Loading & Caching")
    pdf.code_block("""Artifact Path:  models_artifact/{model_version}.pkl
Cache:          In-memory dict (_model_cache), loaded once per model version
Artifact Format: pickle dict with keys:
  - "model":              CalibratedClassifierCV (calibrated probabilities)
  - "raw_model":          XGBClassifier or LGBMClassifier (for SHAP)
  - "feature_columns":    list of 19 feature names
  - "feature_importances": dict of feature importance scores""")

    pdf.subsection("Scoring Pipeline")
    pdf.body_text(
        "1. Load model artifact from disk (with in-memory cache)\n"
        "2. If artifact exists: build numpy array from 19 features, call model.predict_proba()\n"
        "3. If no artifact: run calibrated heuristic fallback\n"
        "4. Compute risk band from calibrated probability\n"
        "5. Generate reason codes from feature thresholds\n"
        "6. Optionally compute SHAP values (TreeExplainer)\n"
        "7. Record FactModelScore to database"
    )

    pdf.subsection("Risk Band Classification")
    pdf.code_block("""probability >= 0.85  -->  "critical"
probability >= 0.65  -->  "high"
probability >= 0.40  -->  "medium"
probability >= 0.20  -->  "low"
probability <  0.20  -->  "minimal" """)

    pdf.subsection("Reason Code Generation")
    reason_data = [
        ("HIGH_CARD_VELOCITY", "card_txn_count_10m >= 5"),
        ("MULTI_ACCOUNT_DEVICE", "device_account_count_30d >= 3"),
        ("MULTI_CARD_IP", "ip_card_count_7d >= 5"),
        ("VPN_PROXY_TOR", "proxy_vpn_tor_flag = True"),
        ("UNUSUAL_AMOUNT", "amount_vs_customer_p95_ratio > 3"),
        ("RAPID_FIRE", "seconds_since_last_txn < 30"),
        ("RISKY_DEVICE", "device_risk_score >= 0.4"),
        ("FRAUD_RING_PROXIMITY", "graph_cluster_risk_score > 0.5"),
        ("GEO_ANOMALY", "geo_distance_from_home_km > 5000"),
        ("HIGH_RISK_MERCHANT", "merchant_chargeback_rate_30d > 0.05"),
        ("BASELINE_RISK", "Default when no specific code applies"),
    ]
    w = [55, 135]
    pdf.table_header(["Reason Code", "Trigger Condition"], w)
    for i, r in enumerate(reason_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Champion / Shadow Model Pattern")
    pdf.body_text(
        "Every scoring request runs TWO model passes:\n\n"
        "1. CHAMPION (xgb-v4.2.0): Calibrated probability is used for the actual decision.\n"
        "   shadow_mode_flag = False. Score affects the decision.\n\n"
        "2. SHADOW (lgb-v5.0.0-rc1): Probability is logged but NOT used for the decision.\n"
        "   shadow_mode_flag = True. Used for offline model comparison.\n\n"
        "Multiple shadow models can be configured via SHADOW_MODEL_VERSIONS (comma-separated). "
        "Shadow scoring enables safe A/B comparison without risk to production decisions."
    )

    pdf.subsection("Heuristic Fallback (When No Model Artifact)")
    pdf.code_block("""Weighted feature scoring:
  card_txn_count_10m:           weight=0.12, threshold=5
  device_account_count_30d:     weight=0.15, threshold=3
  ip_card_count_7d:             weight=0.10, threshold=5
  customer_txn_count_1h:        weight=0.08, threshold=10
  proxy_vpn_tor_flag:           weight=0.12, threshold=1
  device_risk_score:            weight=0.10, threshold=1
  amount_vs_customer_p95_ratio: weight=0.08, threshold=3
  seconds_since_last_txn:       weight=-0.05, threshold=60 (inverse)
  graph_cluster_risk_score:     weight=0.10, threshold=1
  merchant_chargeback_rate_30d: weight=0.10, threshold=0.05

raw_score = SUM(weight * min(value/threshold, 1.0))
calibrated = sigmoid(5 * (raw_score - 0.5))  = 1 / (1 + exp(-5*(raw-0.5)))""")

    # ==================== SECTION 9: GRAPH ENGINE ====================
    pdf.section_title("9", "Graph Intelligence Engine - Fraud Ring Detection")

    pdf.body_text(
        "The Graph Engine builds an account-device-IP-email entity graph using NetworkX. "
        "It detects fraud rings via connected component analysis and computes hop-based risk scores. "
        "Graph data is persisted in graph_entity_node and graph_entity_edge tables."
    )

    pdf.subsection("Node and Edge Types")
    pdf.code_block("""Node Types: account, device, ip, email, card, merchant
Node ID Format: "{type}:{id}"  (e.g., "account:12345", "device:abc-def")

Edge Types:
  account_device   (account <-> device)
  account_ip       (account <-> ip)
  account_email    (account <-> email)
  account_card     (account <-> card)
  device_ip        (device <-> ip)
  device_merchant  (device <-> merchant)

Edges have weight (incremented on each observation) and first/last_seen timestamps.""")

    pdf.subsection("Graph Risk Computation (compute_graph_risk)")
    pdf.code_block("""Input: auth_event_id, account_id, device_id, ip_address, max_hops=2

1. Load full graph from DB into NetworkX (cached per request)
2. Find account node: "account:{account_id}"
3. BFS traversal up to max_hops (default 2) from account node
4. Compute cluster_size = |reachable nodes|
5. Count risky_neighbor_count where node.risk_score > 0.5
6. Compute hop2_risk_score = AVG(risk_score) of neighbors
7. Detect synthetic_identity_flag:
   Pattern: >= 3 accounts + >= 2 devices + <= 1 email in cluster
8. Detect mule_pattern_flag:
   Pattern: >= 4 accounts + any device/IP shared by >= 3 accounts
9. Store FactGraphClusterScore to DB

Output: cluster_id, cluster_size, risky_neighbor_count, hop2_risk_score,
        synthetic_identity_flag, mule_pattern_flag""")

    pdf.subsection("Fraud Ring Detection (find_fraud_rings)")
    pdf.code_block("""1. Find all connected components in the graph
2. Filter: component size >= min_size (default 3)
3. Filter: >= 2 account nodes in component
4. Score each ring:
   ring_score = 0.0
   if accounts >= 3 and shared_devices >= 1:  ring_score += 0.3
   if shared_ips >= 1 and accounts >= 2:       ring_score += 0.2
   ring_score += avg_risk_score * 0.5
5. Filter: ring_score > 0.3
6. Return sorted by ring_score descending""")

    # ==================== SECTION 10: AI COPILOT ====================
    pdf.section_title("10", "AI Investigator Copilot (Claude + Qdrant)")

    pdf.body_text(
        "The AI Copilot assists human fraud investigators with case analysis and recommendations. "
        "It uses Anthropic Claude for reasoning and Qdrant vector DB for similar-case retrieval. "
        "Every step is traced to the agent_trace table for explainability and audit compliance."
    )

    pdf.subsection("Investigation Call Flow")
    pdf.info_box("CALL FLOW: GET /case/{case_id}/investigate", """
Step 1:  Load case from fact_fraud_case (validate exists)
Step 2:  Trace step: "load_case" --> agent_trace table
Step 3:  Gather context:
           |-- Load FactAuthorizationEvent (transaction details)
           |-- Load FactModelScore (all champion + shadow scores)
           |-- Load FactDecision (what decision was made)
           |-- Load FactFraudLabel (any labels/ground truth)
Step 4:  Trace step: "gather_context" --> agent_trace table
Step 5:  Build context text from all gathered data
Step 6:  [CALL TO EMBEDDING SERVICE] OpenAI text-embedding-3-small
           |-- Embed context text (1536 dimensions)
Step 7:  [CALL TO VECTOR MEMORY] Qdrant search_similar_cases
           |-- Query fraud_case_memory collection, top-5 similar
Step 8:  Trace step: "similar_case_retrieval" --> agent_trace table
Step 9:  [CALL TO AI REASONING] Anthropic Claude
           |-- Prompt: analyze risk, key indicators, next steps, confidence
           |-- Model: claude-sonnet-4-20250514 (configurable)
           |-- Fallback: deterministic analysis if API unavailable
Step 10: Trace step: "ai_analysis" --> agent_trace table
Step 11: Return: analysis, similar_cases, trace_steps, latency_ms""")

    pdf.subsection("Recommendation Engine")
    pdf.code_block("""Action recommendations based on probability:
  probability >= 0.85  -->  CONFIRM_FRAUD     (confidence: 0.9)
  probability >= 0.65  -->  ESCALATE          (confidence: 0.7)
  probability >= 0.40  -->  GATHER_MORE_INFO  (confidence: 0.6)
  probability <  0.40  -->  CLOSE_NOT_FRAUD   (confidence: 0.8)""")

    pdf.subsection("Fallback Behavior")
    pdf.body_text(
        "If Qdrant is unavailable: returns empty similar cases list (graceful degradation).\n"
        "If OpenAI is unavailable: returns zero-vector embedding (search still runs).\n"
        "If Anthropic Claude is unavailable: falls back to deterministic analysis with "
        "recommendation to review transaction details and scoring signals manually."
    )

    # ==================== SECTION 11: REPLAY ENGINE ====================
    pdf.section_title("11", "Decision Replay & What-If Engine")

    pdf.body_text(
        "The Replay Engine reconstructs the exact decision as-of transaction time for any historical "
        "transaction. It supports what-if analysis (different model/thresholds) and batch backtesting."
    )

    pdf.subsection("Full Replay (replay_decision)")
    pdf.code_block("""Reconstructs 11 data layers for a given auth_event_id:
  1. Original transaction payload (from fact_authorization_event)
  2. Features at decision time (from fact_transaction_features_online)
  3. All model scores, champion + shadow (from fact_model_score)
  4. All rule firings (from fact_rule_score)
  5. Decision thresholds at time (from dim_model_registry)
  6. Final decision + source (from fact_decision)
  7. Later-arriving labels/ground truth (from fact_fraud_label)
  8. Full lifecycle timeline (from fact_transaction_lifecycle_event)
  9. AI agent traces (from agent_trace)
  10. Decision correctness analysis (was the decision right?)
  11. Time-to-label (seconds between transaction and first label)""")

    pdf.subsection("What-If Comparison (compare_replay)")
    pdf.body_text(
        "Re-scores the same transaction with a different model version and/or different thresholds, "
        "then compares what WOULD have happened vs what actually happened. "
        "Does not persist the re-scored results."
    )

    pdf.subsection("Batch Backtesting (batch_replay)")
    pdf.body_text(
        "Replays many decisions with a specified model version. Aggregates: decisions changed, "
        "approval rate impact, false positive rate, false negative rate, true positives, "
        "true negatives. Essential for model validation before promotion."
    )

    # ==================== SECTION 12: ECONOMICS ENGINE ====================
    pdf.section_title("12", "Fraud Economics Engine - Trading Standpoint")

    pdf.body_text(
        "The Economics Engine translates ML metrics into business P&L metrics that trading desks "
        "and risk managers can directly use for decision-making. It computes prevented fraud, missed fraud, "
        "false positive costs, manual review costs, and net savings."
    )

    pdf.subsection("Key Business Metrics (compute_economics)")
    econ_metrics = [
        ("total_transactions", "Total authorization events in window"),
        ("total_volume_usd", "Sum of billing_amount_usd for all transactions"),
        ("fraud_transactions", "Count of transactions labeled as fraud"),
        ("fraud_volume_usd", "Dollar amount of confirmed fraud"),
        ("prevented_fraud_usd", "Fraud that was declined or sent to review ($)"),
        ("missed_fraud_usd", "Fraud that was approved (leaked through) ($)"),
        ("false_positive_count", "Legitimate transactions wrongly declined"),
        ("false_positive_volume_usd", "Dollar amount of wrongly declined legit txns"),
        ("manual_review_count", "Transactions routed to manual review queue"),
        ("manual_review_cost_usd", "Count * $15.00 per review"),
        ("approval_rate", "Approved / Total (target: >90%)"),
        ("decline_rate", "Declined / Total"),
        ("review_rate", "Manual Review / Total"),
        ("challenge_rate", "Step-up Auth / Total"),
        ("fraud_basis_points", "(fraud_volume / total_volume) * 10,000 bps"),
        ("net_fraud_savings_usd", "prevented - false_positive_vol - review_cost"),
        ("customer_friction_rate", "(declined + stepup + review) / total"),
    ]
    w = [55, 135]
    pdf.table_header(["Metric", "Definition"], w)
    for i, r in enumerate(econ_metrics):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Threshold Sweep (For Traders)")
    pdf.body_text(
        "The threshold sweep simulates what would happen at different decision thresholds. "
        "For each candidate threshold, it reclassifies all scored transactions and computes: "
        "approval_rate, decline_rate, false_positive_rate, missed_fraud_rate, and net_savings_usd.\n\n"
        "This is the key tool for traders to optimize the risk/reward tradeoff. A lower threshold "
        "catches more fraud but increases false positives and customer friction. A higher threshold "
        "lets more fraud through but improves approval rates."
    )

    pdf.subsection("Loss Curve Analysis")
    pdf.body_text(
        "Sorts all scored transactions by fraud probability descending, then at each decile computes: "
        "cumulative fraud caught ($), cumulative false positives (count), cumulative review load. "
        "This shows how much fraud you catch by reviewing the top X% of transactions."
    )

    pdf.subsection("Segmentation Dimensions")
    pdf.bullet("merchant_country_code - Geographic segmentation")
    pdf.bullet("channel - pos, ecommerce, atm, contactless")
    pdf.bullet("auth_type - card_present, card_not_present")
    pdf.bullet("mcc - Merchant Category Code (via dim_merchant join)")
    pdf.bullet("risk_band - critical, high, medium, low, minimal")

    # ==================== SECTION 13: GOVERNANCE ====================
    pdf.section_title("13", "Model Governance & Lifecycle")

    pdf.body_text(
        "The Governance Engine manages the full model lifecycle: registration, evaluation, "
        "approval-gated promotion, A/B experiments, drift monitoring, and model cards."
    )

    pdf.subsection("Model Lifecycle States")
    pdf.code_block("""registered --> staging --> champion (requires approval)
                                 \\-> shadow  (for parallel scoring)
                                 \\-> retired (decommissioned)

Promotion requires:
  - model_version to promote
  - approved_by: identifier of the approver
  - reason: justification for promotion
  Only users with "admin" role can promote models.""")

    pdf.subsection("Model Cards")
    pdf.body_text(
        "Auto-generated documentation for each model version including: training data range, "
        "feature version, evaluation metrics (AUC-ROC, AUC-PR), thresholds, owner, "
        "deployment status, and comparison against other versions."
    )

    pdf.subsection("A/B Experiments")
    pdf.code_block("""ExperimentCreate:
  challenger_model_version: "lgb-v5.0.0-rc1"
  champion_model_version:   "xgb-v4.2.0"
  mode:                     "shadow" | "interleaved"
  traffic_pct:              Percentage of traffic for challenger

Shadow experiments score both models and compare:
  - champion_avg_score vs challenger_avg_score
  - champion_decline_pct vs challenger_decline_pct
  - agreement_pct (how often they agree on approve/decline)""")

    pdf.subsection("Feature Drift Monitoring")
    pdf.body_text(
        "Daily Celery task computes PSI (Population Stability Index) for each of the 19 features. "
        "Compares production distribution (last 7 days) against training distribution (30-120 days ago). "
        "Alert threshold: PSI >= 0.25. Also tracks null_rate, train_mean vs prod_mean."
    )

    # ==================== SECTION 14: CELERY WORKERS ====================
    pdf.section_title("14", "Background Workers (Celery)")

    pdf.body_text(
        "Four background tasks run on the Celery worker pod using synchronous psycopg2 "
        "(not asyncpg, since Celery workers are synchronous)."
    )

    pdf.subsection("Task Definitions")
    task_data = [
        ("backfill_offline_features", "features", "Copy online features to offline store for training"),
        ("generate_label_snapshots", "labels", "Create point-in-time label snapshots for mature transactions"),
        ("compute_drift_metrics", "governance", "Compute per-feature PSI between production and training"),
        ("run_shadow_experiment", "experiments", "Score transactions with champion + challenger, compare"),
    ]
    w = [50, 30, 110]
    pdf.table_header(["Task Name", "Queue", "Description"], w)
    for i, r in enumerate(task_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Worker Configuration")
    pdf.code_block("""Celery Broker: redis://redis:6379/0
Concurrency:   4 workers
Queues:        features, labels, governance, experiments, celery
DB Driver:     psycopg2 (synchronous) with pool_size=5, max_overflow=5
Scheduler:     celery-beat with persistent schedule file""")

    # ==================== SECTION 15: API ENDPOINTS ====================
    pdf.section_title("15", "API Endpoint Reference (44 Endpoints)")

    pdf.subsection("Scoring & Authorization")
    api_data = [
        ("POST", "/authorize/score", "admin, model_risk", "Real-time fraud scoring"),
    ]
    w = [15, 55, 40, 80]
    pdf.table_header(["Method", "Path", "Roles", "Description"], w)
    for r in api_data:
        pdf.table_row(r, w)

    pdf.subsection("Case Management")
    api_data = [
        ("POST", "/case/create", "admin, investigator", "Create fraud case"),
        ("POST", "/case/review", "admin, investigator", "Review/disposition case"),
        ("GET", "/case/{id}/investigate", "admin, investigator", "AI-assisted investigation"),
        ("GET", "/case/{id}/recommend", "admin, investigator", "AI action recommendation"),
    ]
    pdf.table_header(["Method", "Path", "Roles", "Description"], w)
    for i, r in enumerate(api_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Features")
    api_data = [
        ("GET", "/features/get/{id}", "none", "Retrieve stored features"),
        ("POST", "/features/compute", "admin, model_risk", "Compute online features"),
        ("POST", "/features/offline/build", "admin, model_risk", "Build training features"),
    ]
    pdf.table_header(["Method", "Path", "Roles", "Description"], w)
    for i, r in enumerate(api_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Graph Intelligence")
    api_data = [
        ("POST", "/graph/risk", "admin, model_risk, inv", "Compute graph risk"),
        ("GET", "/graph/rings", "none", "Detect fraud rings"),
        ("GET", "/graph/expand/{id}", "none", "Expand cluster"),
        ("POST", "/graph/node", "admin", "Add graph node"),
        ("POST", "/graph/edge", "admin", "Add graph edge"),
    ]
    pdf.table_header(["Method", "Path", "Roles", "Description"], w)
    for i, r in enumerate(api_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Feedback & Labels")
    api_data = [
        ("POST", "/feedback/label", "admin, investigator", "Submit fraud label"),
        ("POST", "/feedback/chargeback", "admin, investigator", "Ingest chargeback"),
    ]
    pdf.table_header(["Method", "Path", "Roles", "Description"], w)
    for i, r in enumerate(api_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Model Governance")
    api_data = [
        ("POST", "/model/register", "admin, model_risk", "Register model"),
        ("POST", "/model/promote", "admin only", "Promote model (approval-gated)"),
        ("POST", "/model/evaluate", "admin, model_risk", "Run evaluation"),
        ("POST", "/model/experiment", "admin, model_risk", "Create A/B experiment"),
        ("GET", "/model/health/{ver}", "none", "Model health metrics"),
    ]
    pdf.table_header(["Method", "Path", "Roles", "Description"], w)
    for i, r in enumerate(api_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Economics")
    api_data = [
        ("GET", "/economics/summary", "none", "Fraud business metrics"),
        ("GET", "/economics/by-segment", "none", "Segmented metrics"),
        ("POST", "/economics/threshold-sweep", "admin, model_risk", "Threshold optimization"),
        ("GET", "/economics/loss-curve", "none", "Loss curve analysis"),
    ]
    pdf.table_header(["Method", "Path", "Roles", "Description"], w)
    for i, r in enumerate(api_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Replay & Parity")
    api_data = [
        ("POST", "/replay/decision/{id}", "admin, mr, inv", "Full decision replay"),
        ("POST", "/replay/compare", "admin, model_risk", "What-if comparison"),
        ("POST", "/replay/batch", "admin, model_risk", "Batch backtesting"),
        ("GET", "/features/parity/report", "none", "Feature parity report"),
        ("GET", "/features/parity/{id}", "none", "Single parity check"),
        ("GET", "/features/registry", "none", "Feature registry (19 features)"),
    ]
    pdf.table_header(["Method", "Path", "Roles", "Description"], w)
    for i, r in enumerate(api_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Governance & Contracts")
    api_data = [
        ("GET", "/governance/model-card/{v}", "admin, mr, ro", "Model card"),
        ("GET", "/governance/model-cards", "none", "List model cards"),
        ("GET", "/governance/compare/{a}/{b}", "none", "Compare models"),
        ("GET", "/governance/contracts", "none", "List data contracts"),
        ("GET", "/governance/contracts/validate", "none", "Validate event schema"),
    ]
    pdf.table_header(["Method", "Path", "Roles", "Description"], w)
    for i, r in enumerate(api_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Dashboard & Observability")
    api_data = [
        ("GET", "/dashboard/transaction/{id}", "none", "360-degree transaction view"),
        ("GET", "/dashboard/transactions", "none", "Search transactions"),
        ("GET", "/dashboard/cases", "none", "Case queue"),
        ("GET", "/dashboard/cases/summary", "none", "Queue summary"),
        ("GET", "/dashboard/models", "none", "Model health dashboard"),
        ("GET", "/dashboard/audit", "none", "Audit trail"),
        ("GET", "/dashboard/ops/summary", "none", "Leadership KPIs"),
        ("GET", "/ops/metrics", "none", "Full metrics dashboard"),
        ("POST", "/ops/metrics/reset", "admin only", "Reset metrics"),
    ]
    pdf.table_header(["Method", "Path", "Roles", "Description"], w)
    for i, r in enumerate(api_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    # ==================== SECTION 16: OBSERVABILITY ====================
    pdf.section_title("16", "Observability, Monitoring & Telemetry")

    pdf.subsection("OpenTelemetry Instrumentation")
    pdf.body_text(
        "All 4 key layers are auto-instrumented:"
    )
    pdf.bold_bullet("FastAPI", "Every HTTP request/response generates a span with method, path, status, latency")
    pdf.bold_bullet("SQLAlchemy", "Every database query generates a span with SQL text and execution time")
    pdf.bold_bullet("Redis", "Every cache get/set generates a span")
    pdf.bold_bullet("Celery", "Every background task generates a span with task name and duration")

    pdf.subsection("Custom Fraud Metrics (Prometheus)")
    metrics = [
        ("fraud.scoring.latency_ms", "Histogram", "End-to-end scoring latency in ms"),
        ("fraud.scoring.requests_total", "Counter", "Total scoring requests"),
        ("fraud.scoring.decisions_total", "Counter", "Decision counts by type (approve/decline/etc)"),
        ("fraud.model.fallbacks_total", "Counter", "Heuristic fallback count (no model artifact)"),
        ("fraud.rules.fires_total", "Counter", "Rule fire count by rule_id"),
        ("fraud.cases.active", "UpDown Counter", "Currently open fraud cases"),
    ]
    w = [55, 30, 105]
    pdf.table_header(["Metric", "Type", "Description"], w)
    for i, r in enumerate(metrics):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Prometheus Endpoint")
    pdf.code_block("""Port: 9464 (configurable via PROMETHEUS_PORT)
Endpoint: http://api:9464/metrics
Scrape interval: recommended 15s""")

    # ==================== SECTION 17: CI/CD ====================
    pdf.section_title("17", "CI/CD Pipeline & Testing")

    pdf.subsection("GitHub Actions Pipeline (.github/workflows/ci.yml)")
    pdf.code_block("""Trigger: push to main, PRs to main

Job 1: LINT (ubuntu-latest, Python 3.12)
  - ruff check src/ tests/ scripts/
  - ruff format --check

Job 2: TEST (depends on lint)
  - Services: PostgreSQL 16, Redis 7
  - Unit tests:        pytest tests/unit/
  - Integration tests: pytest tests/integration/
  - Resilience tests:  pytest tests/resilience/
  - Evaluation tests:  pytest tests/evaluation/ (excl slow)
  - Full coverage:     pytest tests/ --cov=src

Job 3: DOCKER (depends on lint, parallel with test)
  - Build image: fraud-detection-platform:{commit_sha}
  - Smoke test: run container with in-memory SQLite""")

    pdf.subsection("Test Suite Summary (17 Test Files)")
    test_data = [
        ("Unit", "8 files", "Rules engine, graph service, FX, threshold optimizer, etc."),
        ("Integration", "1 file", "Full scoring pipeline end-to-end"),
        ("Routes", "4 files", "Dashboard, economics, governance, observability endpoints"),
        ("Evaluation", "2 files", "Adversarial attacks, eval harness"),
        ("Resilience", "1 file", "Chaos engineering (DB down, API failures, etc.)"),
        ("Load", "1 file", "Locust: 5000 RPS scoring, mixed traffic patterns"),
    ]
    w = [30, 20, 140]
    pdf.table_header(["Category", "Files", "Coverage"], w)
    for i, r in enumerate(test_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    # ==================== SECTION 18: SECURITY ====================
    pdf.section_title("18", "Security: Authentication, RBAC & Rate Limiting")

    pdf.subsection("JWT Authentication")
    pdf.body_text(
        "All protected endpoints require a Bearer JWT token in the Authorization header. "
        "Tokens contain: user_id, role, and exp (expiration). Expired tokens return 401."
    )

    pdf.subsection("Role-Based Access Control (RBAC)")
    role_data = [
        ("admin", "Full access to all endpoints including model promotion and metrics reset"),
        ("model_risk", "Scoring, features, model evaluation, replay, threshold sweep"),
        ("investigator", "Case management, feedback/labels, investigation, graph risk"),
        ("readonly", "Model cards, governance views, dashboards"),
    ]
    w = [35, 155]
    pdf.table_header(["Role", "Permissions"], w)
    for i, r in enumerate(role_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Rate Limiting")
    pdf.code_block("""Scoring endpoints:  5,000 requests/second
Dashboard endpoints: 100 requests/second
Returns HTTP 429 (Too Many Requests) when exceeded""")

    # ==================== SECTION 19: CALL FLOW DIAGRAMS ====================
    pdf.section_title("19", "Call Flow Diagrams (Within & Across Engines)")

    pdf.subsection("Diagram 1: Authorization Scoring (Calls Within Same Engine)")
    pdf.info_box("WITHIN-ENGINE FLOW: ScoringService orchestration (all in API Pod)", """
[ScoringService.score_authorization]
  |
  +---> [1] DB Write: FactAuthorizationEvent
  |
  +---> [2] FeatureService.compute_online_features()   <-- SAME PROCESS CALL
  |        |
  |        +---> DB Read x6: velocity/amount/geo/time/device/IP queries
  |        +---> DB Write: FactTransactionFeaturesOnline
  |
  +---> [3] RulesEngine.evaluate()                     <-- SAME PROCESS CALL
  |        |
  |        +---> Evaluate 8 rules against feature dict (pure Python)
  |        +---> DB Write x8: FactRuleScore records
  |
  +---> [4] FraudModelScorer.score()                   <-- SAME PROCESS CALL
  |        |
  |        +---> Load model from disk cache (or heuristic fallback)
  |        +---> numpy predict_proba() (XGBoost/LightGBM)
  |        +---> DB Write: FactModelScore (champion)
  |
  +---> [5] FraudModelScorer.score_shadow()            <-- SAME PROCESS CALL
  |        |
  |        +---> Same flow as above, shadow_mode=True
  |        +---> DB Write: FactModelScore (shadow)
  |
  +---> [6] Blend: 0.7 * ML + 0.3 * Rules
  +---> [7] Decision: thresholds + high-severity rule override
  +---> [8] If MANUAL_REVIEW: DB Write FactFraudCase
  +---> [9] DB Write: FactDecision
  +---> [10] DB Write: AuditEvent
  +---> Return AuthorizationResponse""")

    pdf.subsection("Diagram 2: Cross-Engine Flows")
    pdf.info_box("CROSS-ENGINE FLOW: Case Investigation (API Pod + External APIs)", """
[API Pod: GET /case/{id}/investigate]
  |
  +---> [1] InvestigatorCopilot (in API Pod)
  |        |
  |        +---> DB Read: FactFraudCase, FactAuthorizationEvent,
  |        |               FactModelScore, FactDecision, FactFraudLabel
  |        |
  |        +---> [EXTERNAL CALL: OpenAI API]
  |        |        text-embedding-3-small --> 1536-dim vector
  |        |
  |        +---> [EXTERNAL CALL: Qdrant Pod]
  |        |        Vector similarity search --> top-5 similar cases
  |        |
  |        +---> [EXTERNAL CALL: Anthropic Claude API]
  |        |        Case analysis prompt --> risk summary + recommendations
  |        |
  |        +---> DB Write x4: agent_trace records (explainability)
  |
  +---> Return: analysis, similar_cases, trace_steps, latency_ms""")

    pdf.info_box("CROSS-ENGINE FLOW: Background Processing (Worker Pod)", """
[Celery Beat Pod: scheduled trigger]
  |
  +---> [REDIS QUEUE] --> enqueue task message
  |
  +---> [Celery Worker Pod: receives task]
           |
           +---> backfill_offline_features:
           |        DB Read: fact_transaction_features_online
           |        DB Write: fact_transaction_features_offline
           |
           +---> generate_label_snapshots:
           |        DB Read: fact_authorization_event, fact_fraud_label
           |        DB Write: fact_label_snapshot
           |
           +---> compute_drift_metrics:
           |        DB Read: online + offline features
           |        Compute PSI per feature (numpy)
           |        DB Write: fact_feature_drift_metric
           |
           +---> run_shadow_experiment:
                    DB Read: online features
                    Score with champion + challenger (model artifacts)
                    DB Write: fact_threshold_experiment""")

    pdf.subsection("Diagram 3: Feedback Loop (Training Data Pipeline)")
    pdf.info_box("FEEDBACK LOOP: From Scoring to Retraining", """
[1] Transaction Scored (real-time)
    |-- FactAuthorizationEvent written
    |-- FactTransactionFeaturesOnline written
    |-- FactModelScore written
    |-- FactDecision written
    |
[2] Label Arrives (days/weeks later)
    |-- POST /feedback/label --> FactFraudLabel written
    |-- POST /feedback/chargeback --> FactChargebackCase written
    |
[3] Label Snapshot (daily Celery task)
    |-- For mature transactions (>N days old)
    |-- Create FactLabelSnapshot with definitive fraud/not-fraud
    |
[4] Offline Feature Backfill (Celery task)
    |-- Copy online features to offline store
    |-- FactTransactionFeaturesOffline written
    |
[5] Model Training (on-demand)
    |-- POST /model/evaluate with training window
    |-- Uses offline features + label snapshots
    |-- Produces new model artifact (.pkl)
    |
[6] Shadow Scoring
    |-- New model registered as shadow
    |-- Scores in parallel, logged but not acted upon
    |
[7] Model Promotion (approval-gated)
    |-- POST /model/promote with approver + reason
    |-- New model becomes champion""")

    # ==================== SECTION 20: TRADING DESK REFERENCE ====================
    pdf.section_title("20", "Trading Desk Reference Guide")

    pdf.body_text(
        "This section provides a trading-desk-friendly summary of how the platform affects "
        "transaction authorization, customer experience, and fraud loss metrics."
    )

    pdf.subsection("How a Transaction Flows (Trading Perspective)")
    pdf.body_text(
        "1. A cardholder taps/swipes/enters card details at a merchant.\n"
        "2. The acquirer sends an authorization request to our platform (POST /authorize/score).\n"
        "3. Within <500ms, the platform:\n"
        "   a) Computes 19 behavioral features from transaction history.\n"
        "   b) Evaluates 8 deterministic fraud rules.\n"
        "   c) Runs the ML model (XGBoost champion + LightGBM shadow).\n"
        "   d) Blends scores: 70% ML + 30% Rules.\n"
        "   e) Makes a decision: APPROVE / STEP_UP / MANUAL_REVIEW / HARD_DECLINE.\n"
        "4. The response is sent back to the acquirer/issuer."
    )

    pdf.subsection("Decision Outcomes & Impact")
    outcome_data = [
        ("APPROVE", "< 0.35", "Transaction goes through. Customer sees no friction."),
        ("STEP_UP", "0.35-0.54", "OTP or 3DS challenge. ~30s customer delay."),
        ("MANUAL_REVIEW", "0.55-0.84", "Transaction held. Investigator reviews within SLA."),
        ("HARD_DECLINE", ">= 0.85", "Transaction blocked immediately. Customer notified."),
    ]
    w = [35, 25, 130]
    pdf.table_header(["Decision", "Score Range", "Customer / Trading Impact"], w)
    for i, r in enumerate(outcome_data):
        pdf.table_row(r, w, fill=(i % 2 == 0))

    pdf.subsection("Key Metrics for Trading Desks")
    pdf.bold_bullet("Fraud Basis Points", "fraud_volume_usd / total_volume_usd * 10,000. Target: < 10 bps")
    pdf.bold_bullet("Approval Rate", "approved / total. Target: > 95% for low-risk segments")
    pdf.bold_bullet("False Positive Rate", "legit_declined / total_legit. Target: < 2%")
    pdf.bold_bullet("Customer Friction Rate", "(declined + stepup + review) / total. Target: < 5%")
    pdf.bold_bullet("Net Fraud Savings", "prevented_fraud - false_positive_loss - review_cost")
    pdf.bold_bullet("Time to Label", "Seconds from transaction to first fraud label")

    pdf.subsection("Threshold Tuning (Direct P&L Impact)")
    pdf.body_text(
        "Traders can request threshold adjustments via POST /economics/threshold-sweep. "
        "Lowering the decline threshold from 0.85 to 0.75 will:\n"
        "- INCREASE prevented fraud (good)\n"
        "- INCREASE false positives and customer friction (bad)\n"
        "- The net effect depends on fraud rate and transaction volumes.\n\n"
        "The threshold sweep endpoint simulates the P&L impact at each threshold level, "
        "so traders can find the optimal risk/reward balance before making changes."
    )

    pdf.subsection("Segmentation for Portfolio Management")
    pdf.body_text(
        "Use GET /economics/by-segment to break down fraud metrics by:\n"
        "- Country (merchant_country_code) - identify high-risk geographies\n"
        "- Channel (pos/ecommerce/atm/contactless) - channel-specific strategies\n"
        "- MCC (merchant category) - industry risk profiles\n"
        "- Auth Type (card_present/card_not_present) - CNP typically higher risk\n"
        "- Risk Band (critical/high/medium/low/minimal) - score distribution analysis"
    )

    pdf.subsection("What Triggers a Fraud Alert (Reason Codes)")
    pdf.body_text(
        "Every scored transaction returns up to 5 human-readable reason codes. "
        "These are the signals that explain WHY the system flagged (or approved) a transaction. "
        "Trading desks should monitor the distribution of reason codes across their portfolio "
        "to identify emerging attack patterns."
    )

    pdf.subsection("Model Performance Monitoring")
    pdf.body_text(
        "- GET /model/health/{version}: Real-time model health (AUC, precision, recall)\n"
        "- GET /governance/model-card/{version}: Full model documentation\n"
        "- GET /governance/compare/{v1}/{v2}: Side-by-side model comparison\n"
        "- POST /replay/batch: Backtest new model against historical transactions\n\n"
        "If model performance degrades (AUC drops, false positive rate rises), the drift "
        "monitoring system will flag it via daily PSI computation. This early warning gives "
        "traders time to adjust thresholds before losses accumulate."
    )

    # ==================== FINAL PAGE ====================
    pdf.add_page()
    pdf.ln(40)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(20, 60, 120)
    pdf.cell(0, 12, "END OF DOCUMENT", align="C")
    pdf.ln(20)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, "Fraud Detection Platform v2.0.0", align="C")
    pdf.ln(8)
    pdf.cell(0, 8, "Technical Architecture & Knowledge Transfer Document", align="C")
    pdf.ln(8)
    pdf.cell(0, 8, "11,962 lines of Python | 28 database tables | 44 API endpoints", align="C")
    pdf.ln(8)
    pdf.cell(0, 8, "9 production engines | 7 containerized services | 17 test suites", align="C")
    pdf.ln(20)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 8, "For questions, contact the Fraud Platform Engineering team.", align="C")

    # Save
    output_path = "/Users/chavala/Fraud Detection system/Fraud_Detection_Platform_Technical_Architecture.pdf"
    pdf.output(output_path)
    print(f"PDF generated: {output_path}")
    print(f"Total pages: {pdf.page_no()}")
    return output_path


if __name__ == "__main__":
    build_document()
