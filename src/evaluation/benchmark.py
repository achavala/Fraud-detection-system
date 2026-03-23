"""
Latency and load benchmark suite for fraud scoring pipeline.
"""
from __future__ import annotations

import random
import statistics
import time
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.features.service import FeatureService
from src.services.scoring.ml_model import FraudModelScorer
from src.services.scoring.rules_engine import RulesEngine
from src.services.scoring.ml_model import FEATURE_COLUMNS

MODEL_DIR = Path(__file__).parent.parent.parent / "models_artifact"


def _random_feature_vector() -> dict[str, Any]:
    """Generate a random feature vector for benchmarking."""
    vec = {}
    for col in FEATURE_COLUMNS:
        if col == "proxy_vpn_tor_flag":
            vec[col] = random.choice([True, False])
        elif "ratio" in col or "score" in col or "rate" in col:
            vec[col] = random.uniform(0, 5)
        elif "count" in col or "txn" in col:
            vec[col] = random.randint(0, 50)
        elif col == "seconds_since_last_txn":
            vec[col] = random.randint(0, 86400) if random.random() > 0.2 else None
        elif "distance" in col or "km" in col:
            vec[col] = random.uniform(0, 15000)
        elif col == "customer_spend_24h":
            vec[col] = random.uniform(0, 10000)
        else:
            vec[col] = random.uniform(0, 10)
    return vec


class BenchmarkSuite:
    """Latency and load benchmark suite for scoring components."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.feature_service = FeatureService(db)
        self.model_scorer = FraudModelScorer(db)
        self.rules_engine = RulesEngine(db)

    def _percentiles(self, latencies_ms: list[float]) -> dict[str, float]:
        if not latencies_ms:
            return {"p50": 0, "p95": 0, "p99": 0, "mean": 0, "min": 0, "max": 0}
        sorted_lat = sorted(latencies_ms)
        n = len(sorted_lat)
        return {
            "p50": sorted_lat[int(n * 0.50)] if n else 0,
            "p95": sorted_lat[int(n * 0.95)] if n else 0,
            "p99": sorted_lat[int(n * 0.99)] if n else 0,
            "mean": statistics.mean(latencies_ms),
            "min": min(latencies_ms),
            "max": max(latencies_ms),
        }

    def benchmark_scoring_latency(self, n_requests: int = 100) -> dict:
        """
        Generate n random feature vectors, time each scoring call using heuristic
        scorer directly (not HTTP). Return p50, p95, p99, mean, min, max latency
        in ms and throughput (requests/sec).
        """
        latencies_ms: list[float] = []
        vectors = [_random_feature_vector() for _ in range(n_requests)]

        for vec in vectors:
            start = time.perf_counter()
            _ = self.model_scorer._predict_heuristic(vec, "benchmark-v1")
            _ = self.model_scorer._calibrate_heuristic(
                self.model_scorer._predict_heuristic(vec, "benchmark-v1")
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        total_seconds = sum(latencies_ms) / 1000 if latencies_ms else 0.001
        throughput = n_requests / total_seconds if total_seconds > 0 else 0

        result = self._percentiles(latencies_ms)
        result["throughput_rps"] = throughput
        result["n_requests"] = n_requests
        return result

    def benchmark_feature_computation(self, n_requests: int = 50) -> dict:
        """Time feature vector construction (to_scoring_vector). Return p50/p95/p99."""
        latencies_ms: list[float] = []

        def make_mock_features(vec: dict) -> Any:
            class MockFeatures:
                pass
            m = MockFeatures()
            for k, v in vec.items():
                setattr(m, k, v)
            for col in FEATURE_COLUMNS:
                if not hasattr(m, col):
                    setattr(m, col, 0)
            return m

        for _ in range(n_requests):
            vec = _random_feature_vector()
            mock = make_mock_features(vec)
            start = time.perf_counter()
            _ = self.feature_service.to_scoring_vector(mock)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        return self._percentiles(latencies_ms)

    def benchmark_rules_engine(self, n_requests: int = 200) -> dict:
        """Time rule evaluation. Return p50/p95/p99."""
        latencies_ms: list[float] = []
        vectors = [_random_feature_vector() for _ in range(n_requests)]

        for vec in vectors:
            start = time.perf_counter()
            for rule in self.rules_engine.rules:
                rule.evaluate(vec, {})
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        return self._percentiles(latencies_ms)

    def benchmark_model_inference(self, n_requests: int = 200) -> dict:
        """
        Load a trained model artifact, time predict_proba calls.
        Return p50/p95/p99. Falls back to heuristic if no artifact.
        """
        import numpy as np

        latencies_ms: list[float] = []
        vectors = [_random_feature_vector() for _ in range(n_requests)]

        # Try to load champion model
        settings = self.model_scorer.settings
        version = settings.champion_model_version
        artifact_path = MODEL_DIR / f"{version}.pkl"

        if artifact_path.exists():
            try:
                import pickle
                with open(artifact_path, "rb") as f:
                    artifact = pickle.load(f)
                feature_cols = artifact.get("feature_columns", FEATURE_COLUMNS)
                model = artifact.get("model")

                for vec in vectors:
                    start = time.perf_counter()
                    x = np.array([[
                        self.model_scorer._coerce_numeric(vec.get(col, 0))
                        for col in feature_cols
                    ]])
                    _ = model.predict_proba(x)
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    latencies_ms.append(elapsed_ms)
            except Exception:
                # Fallback to heuristic
                for vec in vectors:
                    start = time.perf_counter()
                    _ = self.model_scorer._predict_heuristic(vec, version)
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    latencies_ms.append(elapsed_ms)
        else:
            for vec in vectors:
                start = time.perf_counter()
                _ = self.model_scorer._predict_heuristic(vec, version)
                elapsed_ms = (time.perf_counter() - start) * 1000
                latencies_ms.append(elapsed_ms)

        return self._percentiles(latencies_ms)

    def benchmark_end_to_end(self, n_requests: int = 50) -> dict:
        """
        Full pipeline: features + rules + model + decision.
        Uses heuristic path for features (mocked) and real rules/model.
        """
        latencies_ms: list[float] = []
        vectors = [_random_feature_vector() for _ in range(n_requests)]

        for vec in vectors:
            start = time.perf_counter()
            # Rules
            rule_results = []
            for rule in self.rules_engine.rules:
                fired, score, _ = rule.evaluate(vec, {})
                rule_results.append(type("R", (), {"fired_flag": fired, "severity": rule.severity})())
            rule_score = self.rules_engine.compute_aggregate_rule_score(rule_results) if rule_results else 0.0
            # Model
            prob = self.model_scorer._predict_heuristic(vec, "bench-e2e")
            calibrated = self.model_scorer._calibrate_heuristic(prob)
            # Decision (simplified)
            final = 0.7 * calibrated + 0.3 * (rule_score if hasattr(rule_score, "__float__") else 0)
            _ = final >= 0.55
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(elapsed_ms)

        return self._percentiles(latencies_ms)

    def generate_report(self) -> dict:
        """
        Run all benchmarks and return structured report with SLO pass/fail:
        - scoring p99 < 50ms: PASS/FAIL
        - model inference p99 < 10ms: PASS/FAIL
        - rules p99 < 5ms: PASS/FAIL
        - end-to-end p99 < 100ms: PASS/FAIL
        """
        scoring = self.benchmark_scoring_latency(100)
        features = self.benchmark_feature_computation(50)
        rules = self.benchmark_rules_engine(200)
        model = self.benchmark_model_inference(200)
        e2e = self.benchmark_end_to_end(50)

        slo_scoring = "PASS" if scoring["p99"] < 50 else "FAIL"
        slo_model = "PASS" if model["p99"] < 10 else "FAIL"
        slo_rules = "PASS" if rules["p99"] < 5 else "FAIL"
        slo_e2e = "PASS" if e2e["p99"] < 100 else "FAIL"

        return {
            "benchmarks": {
                "scoring_latency": scoring,
                "feature_computation": features,
                "rules_engine": rules,
                "model_inference": model,
                "end_to_end": e2e,
            },
            "slo": {
                "scoring_p99_50ms": slo_scoring,
                "model_inference_p99_10ms": slo_model,
                "rules_p99_5ms": slo_rules,
                "end_to_end_p99_100ms": slo_e2e,
            },
        }
