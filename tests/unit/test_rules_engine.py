"""Tests for the deterministic rules engine."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.scoring.rules_engine import RulesEngine, DEFAULT_RULES, Rule


class TestRuleEvaluation:
    def test_high_velocity_fires(self):
        features = {"card_txn_count_10m": 8}
        rule = DEFAULT_RULES[0]
        fired, score, explanation = rule.evaluate(features, {})
        assert fired is True
        assert "8 times" in explanation

    def test_high_velocity_not_fires(self):
        features = {"card_txn_count_10m": 2}
        rule = DEFAULT_RULES[0]
        fired, _, _ = rule.evaluate(features, {})
        assert fired is False

    def test_vpn_proxy_fires(self):
        features = {"proxy_vpn_tor_flag": True}
        rule = DEFAULT_RULES[2]
        fired, _, explanation = rule.evaluate(features, {})
        assert fired is True
        assert "VPN" in explanation

    def test_rapid_fire_fires(self):
        features = {"seconds_since_last_txn": 10}
        rule = DEFAULT_RULES[5]
        fired, _, _ = rule.evaluate(features, {})
        assert fired is True

    def test_rapid_fire_normal(self):
        features = {"seconds_since_last_txn": 120}
        rule = DEFAULT_RULES[5]
        fired, _, _ = rule.evaluate(features, {})
        assert fired is False

    def test_multi_account_device(self):
        features = {"device_account_count_30d": 5}
        rule = DEFAULT_RULES[1]
        fired, _, _ = rule.evaluate(features, {})
        assert fired is True

    def test_aggregate_score_calculation(self):
        mock_db = AsyncMock()
        engine = RulesEngine(mock_db)

        results = []
        for rule in DEFAULT_RULES[:3]:
            mock = MagicMock()
            mock.fired_flag = True
            mock.severity = rule.severity
            results.append(mock)

        score = engine.compute_aggregate_rule_score(results)
        assert 0 < score <= 1.0

    def test_no_rules_fire_zero_score(self):
        mock_db = AsyncMock()
        engine = RulesEngine(mock_db)
        results = [MagicMock(fired_flag=False, severity="low") for _ in range(5)]
        score = engine.compute_aggregate_rule_score(results)
        assert score == 0.0


class TestMLModel:
    def test_model_predict_low_risk(self):
        from src.services.scoring.ml_model import FraudModelScorer
        scorer = FraudModelScorer.__new__(FraudModelScorer)
        features = {
            "card_txn_count_10m": 0,
            "device_account_count_30d": 0,
            "ip_card_count_7d": 0,
            "proxy_vpn_tor_flag": False,
            "device_risk_score": 0,
            "amount_vs_customer_p95_ratio": 0.5,
            "seconds_since_last_txn": 3600,
            "graph_cluster_risk_score": 0,
            "merchant_chargeback_rate_30d": 0,
            "customer_txn_count_1h": 1,
        }
        prob = scorer._predict(features, "xgb-v4.2.0")
        assert 0 <= prob <= 1

    def test_model_predict_high_risk(self):
        from src.services.scoring.ml_model import FraudModelScorer
        scorer = FraudModelScorer.__new__(FraudModelScorer)
        features = {
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
        prob = scorer._predict(features, "xgb-v4.2.0")
        assert prob > 0.3

    def test_risk_band_assignment(self):
        from src.services.scoring.ml_model import FraudModelScorer
        scorer = FraudModelScorer.__new__(FraudModelScorer)
        assert scorer._compute_risk_band(0.90) == "critical"
        assert scorer._compute_risk_band(0.70) == "high"
        assert scorer._compute_risk_band(0.50) == "medium"
        assert scorer._compute_risk_band(0.25) == "low"
        assert scorer._compute_risk_band(0.10) == "minimal"

    def test_reason_codes_generated(self):
        from src.services.scoring.ml_model import FraudModelScorer
        scorer = FraudModelScorer.__new__(FraudModelScorer)
        features = {
            "card_txn_count_10m": 10,
            "proxy_vpn_tor_flag": True,
            "device_account_count_30d": 0,
            "ip_card_count_7d": 0,
            "amount_vs_customer_p95_ratio": 0,
            "seconds_since_last_txn": 3600,
            "device_risk_score": 0,
            "graph_cluster_risk_score": 0,
        }
        codes = scorer._generate_reason_codes(features, 0.8)
        assert "HIGH_CARD_VELOCITY" in codes
        assert "VPN_PROXY_TOR" in codes
