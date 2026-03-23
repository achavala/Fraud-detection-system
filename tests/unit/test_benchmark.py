"""Tests for the benchmark suite."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.evaluation.benchmark import BenchmarkSuite


@pytest.fixture
def suite():
    mock_db = AsyncMock()
    return BenchmarkSuite(db=mock_db)


def test_scoring_latency_returns_percentiles(suite):
    result = suite.benchmark_scoring_latency(n_requests=20)
    assert "p50" in result
    assert "p95" in result
    assert "p99" in result
    assert "throughput_rps" in result
    assert result["p50"] > 0
    assert result["p99"] >= result["p50"]


def test_rules_engine_latency(suite):
    result = suite.benchmark_rules_engine(n_requests=30)
    assert "p50" in result
    assert result["p99"] < 50  # rules should be sub-50ms


def test_feature_computation_latency(suite):
    result = suite.benchmark_feature_computation(n_requests=10)
    assert "p50" in result
    assert result["p50"] >= 0


def test_end_to_end_latency(suite):
    result = suite.benchmark_end_to_end(n_requests=10)
    assert "p50" in result
    assert result["p99"] < 500  # generous limit for e2e


def test_full_report_structure(suite):
    report = suite.generate_report()
    assert "benchmarks" in report
    assert "slo" in report
    assert "scoring_latency" in report["benchmarks"]
    assert "model_inference" in report["benchmarks"]
    assert "rules_engine" in report["benchmarks"]
    assert "end_to_end" in report["benchmarks"]
    for slo_key in report["slo"]:
        assert report["slo"][slo_key] in ("PASS", "FAIL")
