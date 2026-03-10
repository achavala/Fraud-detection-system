-- =============================================================================
-- Fraud Detection Platform — Production DDL
-- FAANG / Stripe / Amex-grade schema: 29 tables across 9 layers
-- =============================================================================

-- A. Core Business Dimensions
-- ----------------------------

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id         BIGSERIAL PRIMARY KEY,
    external_customer_ref VARCHAR(255) UNIQUE,
    customer_since_dt   DATE,
    kyc_status          VARCHAR(50) DEFAULT 'pending',
    risk_segment        VARCHAR(20) DEFAULT 'low',
    home_country_code   VARCHAR(2),
    home_region         VARCHAR(100),
    birth_year          INTEGER,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_account (
    account_id          BIGSERIAL PRIMARY KEY,
    customer_id         BIGINT NOT NULL REFERENCES dim_customer(customer_id),
    account_status      VARCHAR(50) DEFAULT 'active',
    account_type        VARCHAR(50),
    open_date           DATE,
    close_date          DATE,
    billing_country_code VARCHAR(2),
    autopay_flag        BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_account_customer ON dim_account(customer_id);

CREATE TABLE IF NOT EXISTS dim_card (
    card_id             BIGSERIAL PRIMARY KEY,
    account_id          BIGINT NOT NULL REFERENCES dim_account(account_id),
    pan_token           VARCHAR(255) UNIQUE,
    card_product        VARCHAR(100),
    network             VARCHAR(50),
    card_status         VARCHAR(50) DEFAULT 'active',
    issue_date          DATE,
    expiry_month        INTEGER,
    expiry_year         INTEGER,
    wallet_tokenized_flag BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_card_account ON dim_card(account_id);
CREATE INDEX idx_card_pan_token ON dim_card(pan_token);

CREATE TABLE IF NOT EXISTS dim_merchant (
    merchant_id         BIGSERIAL PRIMARY KEY,
    merchant_name       VARCHAR(500),
    mcc                 VARCHAR(10),
    merchant_category   VARCHAR(200),
    acquirer_id         VARCHAR(100),
    merchant_country_code VARCHAR(2),
    risk_tier           VARCHAR(20) DEFAULT 'standard',
    onboarding_date     DATE,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_merchant_mcc ON dim_merchant(mcc);

CREATE TABLE IF NOT EXISTS dim_device (
    device_id               VARCHAR(255) PRIMARY KEY,
    device_fingerprint      VARCHAR(512),
    os_family               VARCHAR(50),
    app_version             VARCHAR(50),
    browser_family          VARCHAR(100),
    emulator_flag           BOOLEAN DEFAULT FALSE,
    rooted_jailbroken_flag  BOOLEAN DEFAULT FALSE,
    first_seen_at           TIMESTAMPTZ DEFAULT now(),
    last_seen_at            TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_device_fingerprint ON dim_device(device_fingerprint);

CREATE TABLE IF NOT EXISTS dim_ip (
    ip_address          INET PRIMARY KEY,
    geo_country_code    VARCHAR(2),
    geo_region          VARCHAR(200),
    geo_city            VARCHAR(200),
    asn                 VARCHAR(100),
    proxy_vpn_tor_flag  BOOLEAN DEFAULT FALSE,
    hosting_provider_flag BOOLEAN DEFAULT FALSE,
    ip_risk_score       NUMERIC(8,4) DEFAULT 0,
    first_seen_at       TIMESTAMPTZ DEFAULT now(),
    last_seen_at        TIMESTAMPTZ DEFAULT now()
);

-- B. Transaction and Authorization Facts
-- ----------------------------------------

CREATE TABLE IF NOT EXISTS fact_authorization_event (
    auth_event_id       BIGSERIAL PRIMARY KEY,
    transaction_id      BIGINT,
    event_time          TIMESTAMPTZ NOT NULL,
    account_id          BIGINT REFERENCES dim_account(account_id),
    card_id             BIGINT REFERENCES dim_card(card_id),
    customer_id         BIGINT REFERENCES dim_customer(customer_id),
    merchant_id         BIGINT REFERENCES dim_merchant(merchant_id),
    device_id           VARCHAR(255) REFERENCES dim_device(device_id),
    ip_address          INET,
    auth_type           VARCHAR(50),
    channel             VARCHAR(30),
    entry_mode          VARCHAR(30),
    auth_amount         NUMERIC(18,2) NOT NULL,
    currency_code       VARCHAR(3),
    merchant_country_code VARCHAR(2),
    billing_amount_usd  NUMERIC(18,2),
    velocity_bucket     VARCHAR(50),
    auth_status         VARCHAR(30) DEFAULT 'pending',
    decline_reason_code VARCHAR(50),
    challenge_type      VARCHAR(50),
    request_payload_json JSONB,
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_auth_event_time ON fact_authorization_event(event_time);
CREATE INDEX idx_auth_customer ON fact_authorization_event(customer_id);
CREATE INDEX idx_auth_card ON fact_authorization_event(card_id);
CREATE INDEX idx_auth_merchant ON fact_authorization_event(merchant_id);
CREATE INDEX idx_auth_account ON fact_authorization_event(account_id);
CREATE INDEX idx_auth_status ON fact_authorization_event(auth_status);
CREATE INDEX idx_auth_txn_id ON fact_authorization_event(transaction_id);

CREATE TABLE IF NOT EXISTS fact_clearing_event (
    clearing_event_id   BIGSERIAL PRIMARY KEY,
    transaction_id      BIGINT,
    auth_event_id       BIGINT REFERENCES fact_authorization_event(auth_event_id),
    clearing_time       TIMESTAMPTZ NOT NULL,
    clearing_amount     NUMERIC(18,2),
    currency_code       VARCHAR(3),
    settlement_status   VARCHAR(30),
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_clearing_auth ON fact_clearing_event(auth_event_id);

CREATE TABLE IF NOT EXISTS fact_transaction_lifecycle_event (
    lifecycle_event_id  BIGSERIAL PRIMARY KEY,
    transaction_id      BIGINT,
    auth_event_id       BIGINT,
    event_type          VARCHAR(100) NOT NULL,
    event_time          TIMESTAMPTZ NOT NULL,
    actor_type          VARCHAR(50),
    actor_id            VARCHAR(255),
    payload_json        JSONB,
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_lifecycle_auth ON fact_transaction_lifecycle_event(auth_event_id);
CREATE INDEX idx_lifecycle_type ON fact_transaction_lifecycle_event(event_type);

-- C. Feature Store
-- -----------------

CREATE TABLE IF NOT EXISTS fact_transaction_features_online (
    feature_row_id              BIGSERIAL PRIMARY KEY,
    auth_event_id               BIGINT NOT NULL UNIQUE REFERENCES fact_authorization_event(auth_event_id),
    feature_timestamp           TIMESTAMPTZ NOT NULL,
    feature_version             VARCHAR(50) NOT NULL,
    customer_txn_count_1h       INTEGER DEFAULT 0,
    customer_txn_count_24h      INTEGER DEFAULT 0,
    customer_spend_24h          NUMERIC(18,2) DEFAULT 0,
    card_txn_count_10m          INTEGER DEFAULT 0,
    merchant_txn_count_10m      INTEGER DEFAULT 0,
    merchant_chargeback_rate_30d NUMERIC(8,4) DEFAULT 0,
    device_txn_count_1d         INTEGER DEFAULT 0,
    device_account_count_30d    INTEGER DEFAULT 0,
    ip_account_count_7d         INTEGER DEFAULT 0,
    ip_card_count_7d            INTEGER DEFAULT 0,
    geo_distance_from_home_km   NUMERIC(12,3),
    geo_distance_from_last_txn_km NUMERIC(12,3),
    seconds_since_last_txn      BIGINT,
    amount_vs_customer_p95_ratio NUMERIC(12,4),
    amount_vs_merchant_p95_ratio NUMERIC(12,4),
    proxy_vpn_tor_flag          BOOLEAN DEFAULT FALSE,
    device_risk_score           NUMERIC(8,4) DEFAULT 0,
    behavioral_risk_score       NUMERIC(8,4) DEFAULT 0,
    graph_cluster_risk_score    NUMERIC(8,4) DEFAULT 0,
    feature_json                JSONB
);
CREATE INDEX idx_features_online_auth ON fact_transaction_features_online(auth_event_id);

CREATE TABLE IF NOT EXISTS fact_transaction_features_offline (
    offline_feature_row_id  BIGSERIAL PRIMARY KEY,
    auth_event_id           BIGINT NOT NULL,
    as_of_time              TIMESTAMPTZ NOT NULL,
    feature_version         VARCHAR(50) NOT NULL,
    label_snapshot_date     DATE,
    feature_json            JSONB NOT NULL,
    created_at              TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_features_offline_auth ON fact_transaction_features_offline(auth_event_id);

-- D. Model Scoring and Decisioning
-- ----------------------------------

CREATE TABLE IF NOT EXISTS dim_model_registry (
    model_version       VARCHAR(100) PRIMARY KEY,
    model_family        VARCHAR(100),
    model_type          VARCHAR(50),
    training_data_start DATE,
    training_data_end   DATE,
    feature_version     VARCHAR(50),
    threshold_decline   NUMERIC(8,4),
    threshold_review    NUMERIC(8,4),
    threshold_stepup    NUMERIC(8,4),
    deployment_status   VARCHAR(30) DEFAULT 'staging',
    owner               VARCHAR(200),
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fact_model_score (
    score_id                BIGSERIAL PRIMARY KEY,
    auth_event_id           BIGINT NOT NULL REFERENCES fact_authorization_event(auth_event_id),
    model_version           VARCHAR(100) NOT NULL REFERENCES dim_model_registry(model_version),
    score_time              TIMESTAMPTZ NOT NULL,
    fraud_probability       NUMERIC(8,6) NOT NULL,
    calibrated_probability  NUMERIC(8,6),
    predicted_label         BOOLEAN,
    risk_band               VARCHAR(20),
    top_reason_codes        JSONB,
    shap_values_json        JSONB,
    latency_ms              INTEGER,
    shadow_mode_flag        BOOLEAN DEFAULT FALSE,
    created_at              TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_score_auth ON fact_model_score(auth_event_id);
CREATE INDEX idx_score_model ON fact_model_score(model_version);

CREATE TABLE IF NOT EXISTS fact_rule_score (
    rule_score_id       BIGSERIAL PRIMARY KEY,
    auth_event_id       BIGINT NOT NULL REFERENCES fact_authorization_event(auth_event_id),
    rule_set_version    VARCHAR(100),
    rule_id             VARCHAR(100),
    rule_name           VARCHAR(300),
    fired_flag          BOOLEAN DEFAULT FALSE,
    severity            VARCHAR(20),
    contribution_score  NUMERIC(8,4),
    explanation         TEXT,
    score_time          TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_rule_auth ON fact_rule_score(auth_event_id);
CREATE INDEX idx_rule_id ON fact_rule_score(rule_id);

CREATE TABLE IF NOT EXISTS fact_decision (
    decision_id             BIGSERIAL PRIMARY KEY,
    auth_event_id           BIGINT NOT NULL REFERENCES fact_authorization_event(auth_event_id),
    decision_time           TIMESTAMPTZ NOT NULL,
    decision_type           VARCHAR(50) NOT NULL,
    final_risk_score        NUMERIC(8,6),
    decision_source         VARCHAR(50),
    model_version           VARCHAR(100),
    rule_set_version        VARCHAR(100),
    case_id                 BIGINT,
    manual_override_flag    BOOLEAN DEFAULT FALSE,
    manual_override_reason  TEXT,
    created_at              TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_decision_auth ON fact_decision(auth_event_id);
CREATE INDEX idx_decision_type ON fact_decision(decision_type);

-- E. Labels, Disputes, and Truth Management
-- -------------------------------------------

CREATE TABLE IF NOT EXISTS fact_fraud_label (
    label_id                BIGSERIAL PRIMARY KEY,
    auth_event_id           BIGINT NOT NULL REFERENCES fact_authorization_event(auth_event_id),
    transaction_id          BIGINT,
    label_type              VARCHAR(50) NOT NULL,
    is_fraud                BOOLEAN NOT NULL,
    fraud_category          VARCHAR(100),
    fraud_subcategory       VARCHAR(100),
    label_source            VARCHAR(100) NOT NULL,
    source_confidence       NUMERIC(8,4) DEFAULT 1.0,
    event_occurred_at       TIMESTAMPTZ,
    label_received_at       TIMESTAMPTZ NOT NULL,
    effective_label_date    DATE NOT NULL,
    investigator_id         VARCHAR(255),
    notes                   TEXT,
    created_at              TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_label_auth ON fact_fraud_label(auth_event_id);
CREATE INDEX idx_label_date ON fact_fraud_label(effective_label_date);

CREATE TABLE IF NOT EXISTS fact_chargeback_case (
    chargeback_id           BIGSERIAL PRIMARY KEY,
    transaction_id          BIGINT,
    auth_event_id           BIGINT,
    chargeback_reason_code  VARCHAR(50),
    chargeback_amount       NUMERIC(18,2),
    chargeback_received_at  TIMESTAMPTZ NOT NULL,
    representment_flag      BOOLEAN DEFAULT FALSE,
    outcome                 VARCHAR(50),
    outcome_time            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_chargeback_auth ON fact_chargeback_case(auth_event_id);

CREATE TABLE IF NOT EXISTS fact_label_snapshot (
    snapshot_id         BIGSERIAL PRIMARY KEY,
    auth_event_id       BIGINT NOT NULL,
    snapshot_date       DATE NOT NULL,
    label_status        VARCHAR(50),
    is_fraud_snapshot   BOOLEAN,
    maturity_days       INTEGER NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_snapshot_auth ON fact_label_snapshot(auth_event_id);
CREATE INDEX idx_snapshot_date ON fact_label_snapshot(snapshot_date);

-- F. Investigation and Operations
-- --------------------------------

CREATE TABLE IF NOT EXISTS fact_fraud_case (
    case_id         BIGSERIAL PRIMARY KEY,
    auth_event_id   BIGINT NOT NULL REFERENCES fact_authorization_event(auth_event_id),
    case_status     VARCHAR(50) DEFAULT 'open',
    queue_name      VARCHAR(100),
    priority        VARCHAR(20) DEFAULT 'medium',
    assigned_to     VARCHAR(255),
    created_reason  VARCHAR(200),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    closed_at       TIMESTAMPTZ
);
CREATE INDEX idx_case_auth ON fact_fraud_case(auth_event_id);
CREATE INDEX idx_case_status ON fact_fraud_case(case_status);
CREATE INDEX idx_case_queue ON fact_fraud_case(queue_name);

CREATE TABLE IF NOT EXISTS fact_case_action (
    case_action_id  BIGSERIAL PRIMARY KEY,
    case_id         BIGINT NOT NULL REFERENCES fact_fraud_case(case_id),
    action_time     TIMESTAMPTZ NOT NULL,
    action_type     VARCHAR(100) NOT NULL,
    actor_id        VARCHAR(255) NOT NULL,
    payload_json    JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_case_action_case ON fact_case_action(case_id);

-- G. Audit and Agent Trace (Immutable)
-- -------------------------------------

CREATE TABLE IF NOT EXISTS audit_event (
    event_id        BIGSERIAL PRIMARY KEY,
    entity_type     VARCHAR(100) NOT NULL,
    entity_id       VARCHAR(255) NOT NULL,
    event_type      VARCHAR(100) NOT NULL,
    payload_json    JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_audit_entity ON audit_event(entity_type, entity_id);
CREATE INDEX idx_audit_type ON audit_event(event_type);

CREATE TABLE IF NOT EXISTS agent_trace (
    trace_id        BIGSERIAL PRIMARY KEY,
    auth_event_id   BIGINT,
    case_id         BIGINT,
    step_index      INTEGER NOT NULL,
    step_type       VARCHAR(100) NOT NULL,
    input_json      JSONB,
    output_json     JSONB,
    model_name      VARCHAR(100),
    token_usage     JSONB,
    latency_ms      INTEGER,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_trace_case ON agent_trace(case_id);
CREATE INDEX idx_trace_auth ON agent_trace(auth_event_id);

-- H. Graph / Ring Fraud Layer
-- ----------------------------

CREATE TABLE IF NOT EXISTS graph_entity_node (
    node_id         VARCHAR(255) PRIMARY KEY,
    node_type       VARCHAR(50) NOT NULL,
    entity_ref      VARCHAR(255),
    first_seen_at   TIMESTAMPTZ DEFAULT now(),
    last_seen_at    TIMESTAMPTZ DEFAULT now(),
    risk_score      NUMERIC(8,4) DEFAULT 0,
    attributes_json JSONB
);
CREATE INDEX idx_node_type ON graph_entity_node(node_type);

CREATE TABLE IF NOT EXISTS graph_entity_edge (
    edge_id         BIGSERIAL PRIMARY KEY,
    src_node_id     VARCHAR(255) NOT NULL,
    dst_node_id     VARCHAR(255) NOT NULL,
    edge_type       VARCHAR(100) NOT NULL,
    weight          NUMERIC(12,4) DEFAULT 1.0,
    first_seen_at   TIMESTAMPTZ DEFAULT now(),
    last_seen_at    TIMESTAMPTZ DEFAULT now(),
    attributes_json JSONB
);
CREATE INDEX idx_edge_src ON graph_entity_edge(src_node_id);
CREATE INDEX idx_edge_dst ON graph_entity_edge(dst_node_id);
CREATE INDEX idx_edge_type ON graph_entity_edge(edge_type);

CREATE TABLE IF NOT EXISTS fact_graph_cluster_score (
    cluster_score_id        BIGSERIAL PRIMARY KEY,
    auth_event_id           BIGINT NOT NULL,
    cluster_id              VARCHAR(255),
    cluster_size            INTEGER,
    risky_neighbor_count    INTEGER DEFAULT 0,
    hop2_risk_score         NUMERIC(8,4) DEFAULT 0,
    synthetic_identity_flag BOOLEAN DEFAULT FALSE,
    mule_pattern_flag       BOOLEAN DEFAULT FALSE,
    score_time              TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_cluster_auth ON fact_graph_cluster_score(auth_event_id);

-- I. Model Evaluation and Monitoring
-- ------------------------------------

CREATE TABLE IF NOT EXISTS fact_model_eval_metric (
    eval_id             BIGSERIAL PRIMARY KEY,
    model_version       VARCHAR(100) NOT NULL,
    eval_date           DATE NOT NULL,
    segment_name        VARCHAR(100),
    population_name     VARCHAR(100),
    auc_roc             NUMERIC(8,6),
    auc_pr              NUMERIC(8,6),
    precision_at_decline NUMERIC(8,6),
    recall_at_decline   NUMERIC(8,6),
    false_positive_rate NUMERIC(8,6),
    false_negative_rate NUMERIC(8,6),
    approval_rate       NUMERIC(8,6),
    decline_rate        NUMERIC(8,6),
    review_rate         NUMERIC(8,6),
    expected_loss       NUMERIC(18,4),
    prevented_loss      NUMERIC(18,4),
    eval_window_start   TIMESTAMPTZ,
    eval_window_end     TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_eval_model ON fact_model_eval_metric(model_version);
CREATE INDEX idx_eval_date ON fact_model_eval_metric(eval_date);

CREATE TABLE IF NOT EXISTS fact_feature_drift_metric (
    drift_id        BIGSERIAL PRIMARY KEY,
    model_version   VARCHAR(100) NOT NULL,
    feature_name    VARCHAR(200) NOT NULL,
    metric_date     DATE NOT NULL,
    psi             NUMERIC(8,6),
    js_divergence   NUMERIC(8,6),
    null_rate       NUMERIC(8,6),
    train_mean      NUMERIC(18,6),
    prod_mean       NUMERIC(18,6),
    alert_flag      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_drift_model ON fact_feature_drift_metric(model_version);
CREATE INDEX idx_drift_date ON fact_feature_drift_metric(metric_date);

CREATE TABLE IF NOT EXISTS fact_threshold_experiment (
    experiment_id               BIGSERIAL PRIMARY KEY,
    challenger_model_version    VARCHAR(100) NOT NULL,
    champion_model_version      VARCHAR(100) NOT NULL,
    threshold_set_version       VARCHAR(100),
    mode                        VARCHAR(30) NOT NULL,
    start_time                  TIMESTAMPTZ NOT NULL,
    end_time                    TIMESTAMPTZ,
    traffic_pct                 NUMERIC(5,2),
    outcome_summary_json        JSONB,
    created_at                  TIMESTAMPTZ DEFAULT now()
);

-- Prevent any UPDATE/DELETE on immutable tables
CREATE OR REPLACE FUNCTION prevent_mutation() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Table % is immutable — INSERT only', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_event_immutable
    BEFORE UPDATE OR DELETE ON audit_event
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

CREATE TRIGGER lifecycle_event_immutable
    BEFORE UPDATE OR DELETE ON fact_transaction_lifecycle_event
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

CREATE TRIGGER agent_trace_immutable
    BEFORE UPDATE OR DELETE ON agent_trace
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

CREATE TRIGGER case_action_immutable
    BEFORE UPDATE OR DELETE ON fact_case_action
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
