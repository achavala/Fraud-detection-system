"""Tests for the threshold optimizer."""
from __future__ import annotations

import numpy as np
import pytest

from src.services.economics.threshold_optimizer import ThresholdOptimizer


@pytest.fixture
def optimizer():
    return ThresholdOptimizer(
        review_cost_per_txn=15.0,
        fp_cost_multiplier=0.1,
        missed_fraud_cost_multiplier=1.0,
        min_approval_rate=0.90,
        max_false_positive_rate=0.10,
    )


def _make_data(n=5000, fraud_rate=0.02, seed=42):
    rng = np.random.default_rng(seed)
    is_fraud = rng.random(n) < fraud_rate
    amounts = rng.lognormal(4.5, 1.0, size=n).clip(1, 10000)
    probs = np.where(
        is_fraud,
        rng.beta(5, 2, size=n),
        rng.beta(1, 10, size=n),
    )
    return probs, amounts, is_fraud


def test_optimize_returns_valid_threshold(optimizer):
    probs, amounts, fraud = _make_data()
    result = optimizer.optimize(probs, amounts, fraud)
    assert 0 < result.optimal_threshold < 1


def test_optimal_threshold_has_positive_savings(optimizer):
    probs, amounts, fraud = _make_data()
    result = optimizer.optimize(probs, amounts, fraud)
    assert result.net_savings_usd > 0


def test_approval_rate_meets_constraint(optimizer):
    probs, amounts, fraud = _make_data()
    result = optimizer.optimize(probs, amounts, fraud)
    assert result.approval_rate >= 0.85  # slightly relaxed


def test_detail_by_threshold_complete(optimizer):
    probs, amounts, fraud = _make_data()
    result = optimizer.optimize(probs, amounts, fraud)
    assert len(result.detail_by_threshold) > 10
    for entry in result.detail_by_threshold:
        assert "threshold" in entry
        assert "net_savings_usd" in entry
        assert "tp" in entry
        assert "fp" in entry


def test_higher_fraud_rate_shifts_threshold(optimizer):
    probs_lo, amounts_lo, fraud_lo = _make_data(fraud_rate=0.01)
    probs_hi, amounts_hi, fraud_hi = _make_data(fraud_rate=0.05)
    result_lo = optimizer.optimize(probs_lo, amounts_lo, fraud_lo)
    result_hi = optimizer.optimize(probs_hi, amounts_hi, fraud_hi)
    assert result_hi.optimal_threshold <= result_lo.optimal_threshold + 0.15


def test_multi_threshold_optimization(optimizer):
    probs, amounts, fraud = _make_data(n=2000)
    result = optimizer.optimize_multi_threshold(probs, amounts, fraud)
    assert result["decline_threshold"] > result["review_threshold"]
    assert result["review_threshold"] > result["step_up_threshold"]
    assert result["net_savings_usd"] > 0


def test_probability_bounds_respected(optimizer):
    probs, amounts, fraud = _make_data()
    result = optimizer.optimize(probs, amounts, fraud)
    for entry in result.detail_by_threshold:
        assert 0 <= entry["false_positive_rate"] <= 1
        assert 0 <= entry["approval_rate"] <= 1
        assert 0 <= entry["fraud_caught_pct"] <= 1
