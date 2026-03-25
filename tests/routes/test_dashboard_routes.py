"""
HTTP route tests for /dashboard endpoints.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


_DASHBOARD_SVC = "src.api.routes.dashboard.DashboardService"


class TestTransactionDetail:
    def test_returns_200(self, client, admin_token):
        with patch(_DASHBOARD_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.get_transaction_detail.return_value = {
                "auth_event_id": 1, "amount": 99.99
            }
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/dashboard/transaction/1",
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
            assert resp.json()["auth_event_id"] == 1


class TestSearchTransactions:
    def test_default_params_returns_200(self, client, admin_token):
        with patch(_DASHBOARD_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.search_transactions.return_value = {"results": [], "total": 0}
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/dashboard/transactions",
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200

    def test_with_filters(self, client, admin_token):
        with patch(_DASHBOARD_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.search_transactions.return_value = {"results": [], "total": 0}
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/dashboard/transactions",
                params={"customer_id": 1, "min_amount": 50, "limit": 10},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200


class TestCaseQueue:
    def test_returns_200(self, client, admin_token):
        with patch(_DASHBOARD_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.get_case_queue.return_value = {"cases": [], "total": 0}
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/dashboard/cases",
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200


class TestQueueSummary:
    def test_returns_200(self, client, admin_token):
        with patch(_DASHBOARD_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.get_queue_summary.return_value = {"open": 5, "closed": 10}
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/dashboard/cases/summary",
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200


class TestModelHealthDashboard:
    def test_returns_200(self, client, admin_token):
        with patch(_DASHBOARD_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.get_model_health_dashboard.return_value = {"models": []}
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/dashboard/models",
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200


class TestAuditTrail:
    def test_returns_200(self, client, admin_token):
        with patch(_DASHBOARD_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.get_audit_trail.return_value = {"events": []}
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/dashboard/audit",
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200

    def test_with_filters(self, client, admin_token):
        with patch(_DASHBOARD_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.get_audit_trail.return_value = {"events": []}
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/dashboard/audit",
                params={"entity_type": "case", "entity_id": "42"},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200


class TestAgentTraces:
    def test_returns_200(self, client, admin_token):
        with patch(_DASHBOARD_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.get_agent_traces.return_value = {"traces": []}
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/dashboard/traces/1",
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200


class TestOpsSummary:
    def test_returns_200(self, client, admin_token):
        with patch(_DASHBOARD_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.get_ops_summary.return_value = {
                "total_transactions": 1000,
                "fraud_rate_bps": 25,
            }
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/dashboard/ops/summary",
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
