"""Tests for the evaluation harness."""
import pytest
import numpy as np

from src.evaluation.harness import EvaluationHarness, EvalResult


class TestEvaluationHarness:
    def setup_method(self):
        self.harness = EvaluationHarness(threshold_decline=0.85, threshold_review=0.55)

    def test_basic_evaluation(self):
        np.random.seed(42)
        n = 1000
        y_true = [1 if np.random.random() < 0.05 else 0 for _ in range(n)]
        y_score = [
            min(1.0, max(0.0, np.random.random() * 0.3 + (0.5 if t == 1 else 0.0)))
            for t in y_true
        ]

        result = self.harness.evaluate(y_true, y_score, "test-v1.0", "all")

        assert result.model_version == "test-v1.0"
        assert result.sample_size == n
        assert 0 <= result.fraud_rate <= 1
        assert result.auc_roc is not None
        assert 0 <= result.precision <= 1
        assert 0 <= result.recall <= 1
        assert 0 <= result.f1 <= 1

    def test_perfect_classifier(self):
        y_true = [0] * 100 + [1] * 100
        y_score = [0.1] * 100 + [0.9] * 100

        result = self.harness.evaluate(y_true, y_score, "perfect-v1.0")

        assert result.auc_roc is not None
        assert result.auc_roc > 0.95
        assert result.recall > 0.95

    def test_with_amounts(self):
        y_true = [0, 0, 1, 1, 0]
        y_score = [0.1, 0.2, 0.9, 0.8, 0.3]
        amounts = [100, 200, 500, 1000, 150]

        result = self.harness.evaluate(y_true, y_score, "amount-v1.0", amounts=amounts)
        assert result.expected_loss == 1500.0
        assert result.prevented_loss == 1500.0

    def test_model_comparison(self):
        champion = EvalResult(
            model_version="v1.0",
            segment="all",
            sample_size=1000,
            fraud_rate=0.05,
            auc_roc=0.85,
            precision=0.70,
            recall=0.60,
            f1=0.65,
            false_positive_rate=0.05,
            false_negative_rate=0.40,
        )
        challenger = EvalResult(
            model_version="v2.0",
            segment="all",
            sample_size=1000,
            fraud_rate=0.05,
            auc_roc=0.90,
            precision=0.75,
            recall=0.70,
            f1=0.72,
            false_positive_rate=0.04,
            false_negative_rate=0.30,
        )

        comparison = self.harness.compare_models(champion, challenger)
        assert comparison["recommendation"] == "promote"
        assert comparison["improvements"] > 0

    def test_regression_test_passes(self):
        baseline = EvalResult(
            model_version="baseline",
            segment="all",
            sample_size=1000,
            fraud_rate=0.05,
            auc_roc=0.85,
            precision=0.70,
            recall=0.60,
            f1=0.65,
        )
        current = EvalResult(
            model_version="current",
            segment="all",
            sample_size=1000,
            fraud_rate=0.05,
            auc_roc=0.86,
            precision=0.71,
            recall=0.61,
            f1=0.66,
        )

        result = self.harness.regression_test(baseline, current)
        assert result["passed"] is True

    def test_regression_test_fails(self):
        baseline = EvalResult(
            model_version="baseline",
            segment="all",
            sample_size=1000,
            fraud_rate=0.05,
            auc_roc=0.85,
            precision=0.70,
            recall=0.60,
            f1=0.65,
        )
        current = EvalResult(
            model_version="degraded",
            segment="all",
            sample_size=1000,
            fraud_rate=0.05,
            auc_roc=0.75,
            precision=0.50,
            recall=0.40,
            f1=0.44,
        )

        result = self.harness.regression_test(baseline, current, max_regression_pct=5.0)
        assert result["passed"] is False
        assert len(result["regressions"]) > 0
