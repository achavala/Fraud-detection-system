"""
HTTP route tests for /ops (observability) endpoints.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.middleware.auth import create_access_token


@pytest.fixture
def client():
    from src.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def admin_token():
    return create_access_token("test-admin", "admin")


@pytest.fixture
def readonly_token():
    return create_access_token("test-reader", "readonly")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestMetricsEndpoints:
    def test_full_dashboard(self, client, admin_token):
        resp = client.get("/ops/metrics", headers=_auth(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert "scoring" in data
        assert "decisions" in data
        assert "rules" in data

    def test_scoring_metrics(self, client, admin_token):
        resp = client.get("/ops/metrics/scoring", headers=_auth(admin_token))
        assert resp.status_code == 200

    def test_decision_metrics(self, client, admin_token):
        resp = client.get("/ops/metrics/decisions", headers=_auth(admin_token))
        assert resp.status_code == 200

    def test_rule_metrics(self, client, admin_token):
        resp = client.get("/ops/metrics/rules", headers=_auth(admin_token))
        assert resp.status_code == 200

    def test_parity_metrics(self, client, admin_token):
        resp = client.get("/ops/metrics/parity", headers=_auth(admin_token))
        assert resp.status_code == 200

    def test_api_metrics(self, client, admin_token):
        resp = client.get("/ops/metrics/api", headers=_auth(admin_token))
        assert resp.status_code == 200


class TestMetricsReset:
    def test_reset_requires_admin(self, client, readonly_token):
        resp = client.post("/ops/metrics/reset", headers=_auth(readonly_token))
        assert resp.status_code == 403

    def test_reset_with_admin(self, client, admin_token):
        resp = client.post("/ops/metrics/reset", headers=_auth(admin_token))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
