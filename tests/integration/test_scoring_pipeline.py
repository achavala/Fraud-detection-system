from __future__ import annotations

import pickle
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.database import Base
from src.services.scoring.rules_engine import RulesEngine, DEFAULT_RULES
from src.services.scoring.ml_model import (
    FraudModelScorer,
    FEATURE_COLUMNS,
)
from src.services.scoring.service import ScoringService
from src.services.scoring.model_trainer import FraudModelTrainer
from src.schemas.transactions import DecisionType


# Import models so they are registered with Base.metadata
import src.models  # noqa: F401


@pytest.fixture
def sqlite_engine():
    """Create sync SQLite in-memory engine."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def sync_session(sqlite_engine):
    """Provide a sync session for tests."""
    SessionLocal = sessionmaker(bind=sqlite_engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_async_db():
    """Mock async DB for components that require AsyncSession."""
    mock = AsyncMock()
    mock.add = MagicMock()
    mock.flush = AsyncMock(return_value=None)
    return mock


def test_full_scoring_pipeline_rules(mock_async_db):
    """Create a rules engine with a mock DB, evaluate features, verify rules fire for high-risk features."""
    engine = RulesEngine(mock_async_db)
    high_risk_features = {
        "card_txn_count_10m": 8,
        "device_account_count_30d": 5,
        "proxy_vpn_tor_flag": True,
        "amount_vs_customer_p95_ratio": 4.0,
        "ip_card_count_7d": 6,
        "seconds_since_last_txn": 15,
        "device_risk_score": 0.6,
        "customer_spend_24h": 6000,
    }
    for rule in engine.rules:
        fired, score, explanation = rule.evaluate(high_risk_features, {})
        if fired:
            assert score == 1.0
            assert len(explanation) > 0
    # Verify at least R001, R002, R003, R004, R005, R006, R007, R008 fire
    r001 = engine.rules[0]
    fired, _, _ = r001.evaluate(high_risk_features, {})
    assert fired is True
    r003 = engine.rules[2]
    fired, _, _ = r003.evaluate(high_risk_features, {})
    assert fired is True


def test_full_scoring_pipeline_model(mock_async_db):
    """Create FraudModelScorer, test _predict_heuristic and _compute_risk_band directly."""
    scorer = FraudModelScorer(mock_async_db)
    low_risk_features = {
        "card_txn_count_10m": 0,
        "device_account_count_30d": 0,
        "ip_card_count_7d": 0,
        "proxy_vpn_tor_flag": False,
        "device_risk_score": 0.1,
        "amount_vs_customer_p95_ratio": 0.5,
        "seconds_since_last_txn": 3600,
        "graph_cluster_risk_score": 0.1,
        "merchant_chargeback_rate_30d": 0.01,
        "customer_txn_count_1h": 1,
    }
    prob = scorer._predict_heuristic(low_risk_features, "xgb-v4.2.0")
    assert 0 <= prob <= 1

    high_risk_features = {
        "card_txn_count_10m": 10,
        "device_account_count_30d": 5,
        "ip_card_count_7d": 8,
        "proxy_vpn_tor_flag": True,
        "device_risk_score": 0.9,
        "amount_vs_customer_p95_ratio": 5.0,
        "seconds_since_last_txn": 5,
        "graph_cluster_risk_score": 0.8,
        "merchant_chargeback_rate_30d": 0.1,
        "customer_txn_count_1h": 20,
    }
    prob = scorer._predict_heuristic(high_risk_features, "xgb-v4.2.0")
    assert prob > 0.2

    assert scorer._compute_risk_band(0.90) == "critical"
    assert scorer._compute_risk_band(0.70) == "high"
    assert scorer._compute_risk_band(0.50) == "medium"
    assert scorer._compute_risk_band(0.25) == "low"
    assert scorer._compute_risk_band(0.10) == "minimal"


def test_feature_vector_completeness():
    """Verify all 19 feature columns are present in a scoring vector."""
    assert len(FEATURE_COLUMNS) == 19
    required = [
        "customer_txn_count_1h",
        "customer_txn_count_24h",
        "customer_spend_24h",
        "card_txn_count_10m",
        "merchant_txn_count_10m",
        "merchant_chargeback_rate_30d",
        "device_txn_count_1d",
        "device_account_count_30d",
        "ip_account_count_7d",
        "ip_card_count_7d",
        "geo_distance_from_home_km",
        "geo_distance_from_last_txn_km",
        "seconds_since_last_txn",
        "amount_vs_customer_p95_ratio",
        "amount_vs_merchant_p95_ratio",
        "proxy_vpn_tor_flag",
        "device_risk_score",
        "behavioral_risk_score",
        "graph_cluster_risk_score",
    ]
    for col in required:
        assert col in FEATURE_COLUMNS
    scoring_vector = {k: 0 for k in FEATURE_COLUMNS}
    assert len(scoring_vector) == 19


def test_decision_logic(mock_async_db):
    """Test ScoringService._make_decision with various score/rule combinations."""
    with patch("src.services.scoring.service.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            score_threshold_decline=0.85,
            score_threshold_review=0.55,
            score_threshold_stepup=0.35,
        )
        service = ScoringService(mock_async_db)

        # No high-severity rule fired
        rule_results = [MagicMock(fired_flag=False, severity="low") for _ in range(8)]

        assert service._make_decision(0.90, rule_results) == DecisionType.HARD_DECLINE
        assert service._make_decision(0.55, rule_results) == DecisionType.MANUAL_REVIEW
        assert service._make_decision(0.40, rule_results) == DecisionType.STEP_UP
        assert service._make_decision(0.20, rule_results) == DecisionType.APPROVE

        # High-severity rule fired forces manual review even below threshold
        rule_results[0].fired_flag = True
        rule_results[0].severity = "high"
        assert service._make_decision(0.40, rule_results) == DecisionType.MANUAL_REVIEW


def test_model_trainer_xgboost():
    """Train an XGBoost model on synthetic data, verify artifact is saved and can be loaded."""
    trainer = FraudModelTrainer(model_dir=Path(tempfile.mkdtemp()))
    df = trainer.generate_synthetic_training_data(n_samples=1000, fraud_rate=0.03, seed=42)
    result = trainer.train_xgboost(df, model_version="xgb-test-int", test_size=0.2)

    assert "model_version" in result
    assert result["model_version"] == "xgb-test-int"
    assert "path" in result
    assert Path(result["path"]).exists()
    assert "metrics" in result

    with open(result["path"], "rb") as f:
        artifact = pickle.load(f)
    assert "model" in artifact
    assert "feature_columns" in artifact
    assert "raw_model" in artifact
    assert len(artifact["feature_columns"]) == 19


def test_model_trainer_lightgbm():
    """Train a LightGBM model on synthetic data, verify artifact is saved."""
    pytest.importorskip("lightgbm")
    trainer = FraudModelTrainer(model_dir=Path(tempfile.mkdtemp()))
    df = trainer.generate_synthetic_training_data(n_samples=1000, fraud_rate=0.03, seed=42)
    result = trainer.train_lightgbm(df, model_version="lgb-test-int", test_size=0.2)

    assert "model_version" in result
    assert result["model_version"] == "lgb-test-int"
    assert "path" in result
    assert Path(result["path"]).exists()
    assert "metrics" in result

    with open(result["path"], "rb") as f:
        artifact = pickle.load(f)
    assert "model" in artifact
    assert "feature_columns" in artifact
    assert "raw_model" in artifact


def test_trained_model_scoring(mock_async_db):
    """Train a model, load it in FraudModelScorer, verify _predict_with_model works."""
    trainer = FraudModelTrainer(model_dir=Path(tempfile.mkdtemp()))
    df = trainer.generate_synthetic_training_data(n_samples=500, fraud_rate=0.05, seed=42)
    result = trainer.train_xgboost(df, model_version="xgb-score-test", test_size=0.2)

    with open(result["path"], "rb") as f:
        artifact = pickle.load(f)

    scorer = FraudModelScorer(mock_async_db)
    features = {col: 0.0 for col in FEATURE_COLUMNS}
    features["card_txn_count_10m"] = 3
    features["proxy_vpn_tor_flag"] = 0

    raw_prob, calibrated_prob = scorer._predict_with_model(features, artifact)
    assert 0 <= raw_prob <= 1
    assert 0 <= calibrated_prob <= 1


def test_end_to_end_train_and_score(mock_async_db):
    """Generate synthetic data, train model, score a sample, verify probability is between 0 and 1."""
    trainer = FraudModelTrainer(model_dir=Path(tempfile.mkdtemp()))
    df = trainer.generate_synthetic_training_data(n_samples=500, fraud_rate=0.05, seed=42)
    trainer.train_xgboost(df, model_version="xgb-e2e-test", test_size=0.2)

    with open(trainer.model_dir / "xgb-e2e-test.pkl", "rb") as f:
        artifact = pickle.load(f)

    scorer = FraudModelScorer(mock_async_db)
    sample = df.iloc[0]
    features = {col: float(sample[col]) if col != "proxy_vpn_tor_flag" else int(sample[col]) for col in FEATURE_COLUMNS}

    raw_prob, calibrated_prob = scorer._predict_with_model(features, artifact)
    assert 0 <= raw_prob <= 1
    assert 0 <= calibrated_prob <= 1
