"""
Locust load testing for the Fraud Detection Platform.

Usage:
    # Web UI mode (browse to http://localhost:8089)
    locust -f tests/load/locustfile.py --host http://localhost:8000

    # Headless mode — 100 users, 10 spawn/sec, 2 min run
    locust -f tests/load/locustfile.py --host http://localhost:8000 \
        --users 100 --spawn-rate 10 --run-time 2m --headless
"""
from __future__ import annotations

import random
import time

from locust import HttpUser, between, task, tag

_CHANNELS = ["pos", "ecommerce", "atm", "contactless"]
_CURRENCIES = ["USD", "EUR", "GBP", "CAD"]


def _make_auth_request() -> dict:
    return {
        "transaction_id": random.randint(100_000, 999_999),
        "account_id": random.randint(1, 5000),
        "card_id": random.randint(1, 10000),
        "customer_id": random.randint(1, 5000),
        "merchant_id": random.randint(1, 2000),
        "auth_amount": round(random.uniform(1.0, 5000.0), 2),
        "currency_code": random.choice(_CURRENCIES),
        "merchant_country_code": "US",
        "mcc": str(random.choice([5411, 5812, 5999, 7011, 4111])),
        "channel": random.choice(_CHANNELS),
        "auth_type": "card_present",
        "entry_mode": random.choice(["chip", "contactless", "keyed"]),
        "device_id": f"dev-{random.randint(1, 3000)}",
        "ip_address": f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
    }


class FraudPlatformUser(HttpUser):
    """Simulates a mix of read and write traffic against the platform."""

    wait_time = between(0.1, 1.0)

    def on_start(self):
        self.token = self._get_token()

    def _get_token(self) -> str:
        from jose import jwt
        from datetime import datetime, timedelta

        payload = {
            "user_id": f"loadtest-{random.randint(1, 1000)}",
            "role": "admin",
            "exp": datetime.utcnow() + timedelta(hours=24),
        }
        return jwt.encode(payload, "change-me", algorithm="HS256")

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @task(10)
    @tag("scoring")
    def score_transaction(self):
        self.client.post(
            "/authorize/score",
            json=_make_auth_request(),
            headers=self._headers,
        )

    @task(5)
    @tag("dashboard")
    def get_transactions(self):
        self.client.get(
            "/dashboard/transactions",
            params={"limit": 20},
            headers=self._headers,
        )

    @task(3)
    @tag("dashboard")
    def get_case_queue(self):
        self.client.get(
            "/dashboard/cases",
            params={"status": "open", "limit": 20},
            headers=self._headers,
        )

    @task(3)
    @tag("dashboard")
    def get_queue_summary(self):
        self.client.get(
            "/dashboard/cases/summary",
            headers=self._headers,
        )

    @task(2)
    @tag("dashboard")
    def get_ops_summary(self):
        self.client.get(
            "/dashboard/ops/summary",
            headers=self._headers,
        )

    @task(2)
    @tag("observability")
    def get_metrics(self):
        self.client.get(
            "/ops/metrics",
            headers=self._headers,
        )

    @task(2)
    @tag("observability")
    def get_scoring_metrics(self):
        self.client.get(
            "/ops/metrics/scoring",
            headers=self._headers,
        )

    @task(1)
    @tag("dashboard")
    def get_model_health_dashboard(self):
        self.client.get(
            "/dashboard/models",
            headers=self._headers,
        )

    @task(1)
    @tag("dashboard")
    def get_audit_trail(self):
        self.client.get(
            "/dashboard/audit",
            params={"limit": 50},
            headers=self._headers,
        )

    @task(1)
    @tag("health")
    def health_check(self):
        self.client.get("/health")


class ScoringOnlyUser(HttpUser):
    """High-throughput scoring-only user for pure latency benchmarks."""

    wait_time = between(0.01, 0.05)

    def on_start(self):
        from jose import jwt
        from datetime import datetime, timedelta

        payload = {
            "user_id": f"scoring-bot-{random.randint(1, 100)}",
            "role": "admin",
            "exp": datetime.utcnow() + timedelta(hours=24),
        }
        self.token = jwt.encode(payload, "change-me", algorithm="HS256")

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @task
    @tag("scoring")
    def score_transaction(self):
        self.client.post(
            "/authorize/score",
            json=_make_auth_request(),
            headers=self._headers,
        )
