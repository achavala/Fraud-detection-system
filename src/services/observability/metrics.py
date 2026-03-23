"""
Observability pack — runtime metrics collection.
Singleton in-memory metrics with no external dependencies.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any

MAX_LATENCY_SAMPLES = 10_000


def _percentile(sorted_arr: list[float], p: float) -> float:
    """Compute percentile of sorted array. Returns 0 if empty."""
    if not sorted_arr:
        return 0.0
    idx = (p / 100) * (len(sorted_arr) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_arr) - 1)
    frac = idx - lo
    return sorted_arr[lo] * (1 - frac) + sorted_arr[hi] * frac


class PlatformMetrics:
    """
    Singleton that collects real-time operational metrics.
    Uses simple in-memory counters (no external deps).
    """

    _instance: PlatformMetrics | None = None
    _lock = threading.Lock()

    def __new__(cls) -> PlatformMetrics:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._lock = threading.Lock()
        # Scoring latency samples: rolling window
        self._latency_samples: deque[tuple[float, str]] = deque(maxlen=MAX_LATENCY_SAMPLES)
        # Fallbacks: (model_version, reason)
        self._scoring_fallbacks: list[tuple[str, str]] = []
        # Copilot: invocations (for total) and fallbacks
        self._copilot_invocations: list[int] = []
        self._copilot_fallbacks: list[int] = []
        # Rule fires: rule names
        self._rule_fires: list[str] = []
        # Decisions: decision types
        self._decisions: list[str] = []
        # Parity failures: (feature_name, delta)
        self._parity_failures: list[tuple[str, float]] = []
        # API requests: (endpoint, status_code, latency_ms)
        self._api_requests: list[tuple[str, int, float]] = []
        self._initialized = True

    def record_scoring_latency(self, latency_ms: float, model_version: str) -> None:
        """Record one scoring call latency."""
        with self._lock:
            self._latency_samples.append((latency_ms, model_version))

    def record_scoring_fallback(self, model_version: str, reason: str) -> None:
        """Record a heuristic fallback."""
        with self._lock:
            self._scoring_fallbacks.append((model_version, reason))

    def record_copilot_invocation(self) -> None:
        """Record a copilot call (for total-calls denominator)."""
        with self._lock:
            self._copilot_invocations.append(1)

    def record_copilot_fallback(self, case_id: int) -> None:
        """Record a deterministic copilot fallback."""
        with self._lock:
            self._copilot_fallbacks.append(case_id)

    def record_rule_fire(self, rule_name: str) -> None:
        """Record a rule firing."""
        with self._lock:
            self._rule_fires.append(rule_name)

    def record_decision(self, decision_type: str) -> None:
        """Record a decision distribution entry."""
        with self._lock:
            self._decisions.append(decision_type)

    def record_parity_failure(self, feature_name: str, delta: float) -> None:
        """Record a parity violation."""
        with self._lock:
            self._parity_failures.append((feature_name, delta))

    def record_api_request(
        self, endpoint: str, status_code: int, latency_ms: float
    ) -> None:
        """Record API call."""
        with self._lock:
            self._api_requests.append((endpoint, status_code, latency_ms))

    def get_scoring_metrics(self) -> dict[str, Any]:
        """Return p50/p95/p99 latency, total calls, fallback count, fallback rate, by-model breakdown."""
        with self._lock:
            latencies = [x[0] for x in self._latency_samples]
            model_counts: dict[str, int] = {}
            for _, v in self._latency_samples:
                model_counts[v] = model_counts.get(v, 0) + 1
            total_calls = len(self._latency_samples)
            fallback_count = len(self._scoring_fallbacks)
            fallback_rate = fallback_count / total_calls if total_calls > 0 else 0.0

        sorted_lat = sorted(latencies) if latencies else []
        return {
            "p50_latency_ms": round(_percentile(sorted_lat, 50), 2),
            "p95_latency_ms": round(_percentile(sorted_lat, 95), 2),
            "p99_latency_ms": round(_percentile(sorted_lat, 99), 2),
            "total_calls": total_calls,
            "fallback_count": fallback_count,
            "fallback_rate": round(fallback_rate, 4),
            "by_model": model_counts,
        }

    def get_decision_distribution(self) -> dict[str, Any]:
        """Return count per decision_type, approval rate, decline rate, review rate."""
        with self._lock:
            decisions = list(self._decisions)

        total = len(decisions)
        counts: dict[str, int] = {}
        for d in decisions:
            counts[d] = counts.get(d, 0) + 1

        approvals = sum(
            c for k, c in counts.items()
            if "approve" in k.lower() and "decline" not in k.lower()
        )
        declines = sum(
            c for k, c in counts.items()
            if "decline" in k.lower()
        )
        reviews = sum(
            c for k, c in counts.items()
            if "review" in k.lower()
        )

        return {
            "by_decision_type": counts,
            "total": total,
            "approval_rate": round(approvals / total, 4) if total > 0 else 0.0,
            "decline_rate": round(declines / total, 4) if total > 0 else 0.0,
            "review_rate": round(reviews / total, 4) if total > 0 else 0.0,
        }

    def get_rule_fire_rates(self) -> dict[str, Any]:
        """Return count per rule, top 10 by frequency."""
        with self._lock:
            fires = list(self._rule_fires)

        counts: dict[str, int] = {}
        for r in fires:
            counts[r] = counts.get(r, 0) + 1

        top_10 = sorted(
            counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        return {
            "by_rule": counts,
            "top_10_by_frequency": dict(top_10),
            "total_fires": len(fires),
        }

    def get_parity_metrics(self) -> dict[str, Any]:
        """Return total failures, by-feature failure counts, worst features."""
        with self._lock:
            failures = list(self._parity_failures)

        total = len(failures)
        by_feature: dict[str, int] = {}
        by_feature_delta: dict[str, list[float]] = {}
        for name, delta in failures:
            by_feature[name] = by_feature.get(name, 0) + 1
            by_feature_delta.setdefault(name, []).append(delta)

        worst = sorted(
            by_feature.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        return {
            "total_failures": total,
            "by_feature": by_feature,
            "worst_features": dict(worst),
        }

    def get_copilot_metrics(self) -> dict[str, Any]:
        """Return total calls, fallback count, fallback rate."""
        with self._lock:
            fallbacks = list(self._copilot_fallbacks)
            total_calls = len(self._copilot_invocations)

        fallback_count = len(fallbacks)
        return {
            "total_calls": total_calls,
            "fallback_count": fallback_count,
            "fallback_rate": round(
                fallback_count / total_calls, 4
            ) if total_calls > 0 else 0.0,
        }

    def get_api_metrics(self) -> dict[str, Any]:
        """Return total requests, by-endpoint count, avg latency, error rate."""
        with self._lock:
            requests = list(self._api_requests)

        total = len(requests)
        by_endpoint: dict[str, list[tuple[int, float]]] = {}
        for ep, status, lat in requests:
            by_endpoint.setdefault(ep, []).append((status, lat))

        endpoint_stats: dict[str, dict[str, Any]] = {}
        for ep, data in by_endpoint.items():
            statuses = [x[0] for x in data]
            lats = [x[1] for x in data]
            errors = sum(1 for s in statuses if s >= 400)
            endpoint_stats[ep] = {
                "count": len(data),
                "avg_latency_ms": round(sum(lats) / len(lats), 2) if lats else 0,
                "error_count": errors,
                "error_rate": round(errors / len(data), 4) if data else 0,
            }

        total_errors = sum(
            1 for _, status, _ in requests if status >= 400
        )
        all_lats = [x[2] for x in requests]
        avg_lat = sum(all_lats) / len(all_lats) if all_lats else 0

        return {
            "total_requests": total,
            "by_endpoint": endpoint_stats,
            "avg_latency_ms": round(avg_lat, 2),
            "error_rate": round(total_errors / total, 4) if total > 0 else 0,
        }

    def get_full_dashboard(self) -> dict[str, Any]:
        """Aggregate all metrics into a single dashboard payload."""
        return {
            "scoring": self.get_scoring_metrics(),
            "decisions": self.get_decision_distribution(),
            "rules": self.get_rule_fire_rates(),
            "parity": self.get_parity_metrics(),
            "copilot": self.get_copilot_metrics(),
            "api": self.get_api_metrics(),
        }

    def reset(self) -> None:
        """Clear all counters (for testing)."""
        with self._lock:
            self._latency_samples.clear()
            self._scoring_fallbacks.clear()
            self._copilot_invocations.clear()
            self._copilot_fallbacks.clear()
            self._rule_fires.clear()
            self._decisions.clear()
            self._parity_failures.clear()
            self._api_requests.clear()
