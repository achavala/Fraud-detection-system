"""
HTTP route tests for /economics endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
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


@pytest.fixture
def readonly_token():
    return create_access_token("test-reader", "readonly")


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestEconomicsSummary:
    def test_summary_returns_200(self, client, admin_token):
        with patch(
            "src.api.routes.economics.FraudEconomicsService"
        ) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.compute_economics.return_value = {
                "prevented_fraud_usd": 500.0,
                "missed_fraud_usd": 100.0,
            }
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/economics/summary",
                params={
                    "start_time": "2024-01-01T00:00:00Z",
                    "end_time": "2024-12-31T23:59:59Z",
                },
                headers=_auth_header(admin_token),
            )
            assert resp.status_code == 200
            assert "prevented_fraud_usd" in resp.json()

    def test_summary_missing_params_returns_422(self, client, admin_token):
        resp = client.get(
            "/economics/summary",
            headers=_auth_header(admin_token),
        )
        assert resp.status_code == 422


class TestEconomicsBySegment:
    def test_by_segment_returns_200(self, client, admin_token):
        with patch(
            "src.api.routes.economics.FraudEconomicsService"
        ) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.compute_economics_by_segment.return_value = [
                {"segment": "US", "total": 1000}
            ]
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/economics/by-segment",
                params={
                    "start_time": "2024-01-01T00:00:00Z",
                    "end_time": "2024-12-31T23:59:59Z",
                    "segment_by": "merchant_country_code",
                },
                headers=_auth_header(admin_token),
            )
            assert resp.status_code == 200


class TestThresholdSweep:
    def test_sweep_requires_auth(self, client):
        resp = client.post(
            "/economics/threshold-sweep",
            json={
                "start_time": "2024-01-01T00:00:00Z",
                "end_time": "2024-12-31T23:59:59Z",
                "thresholds": [0.3, 0.5, 0.7, 0.9],
            },
        )
        assert resp.status_code in (401, 403)

    def test_sweep_with_auth_returns_200(self, client, admin_token):
        with patch(
            "src.api.routes.economics.FraudEconomicsService"
        ) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.compute_threshold_economics.return_value = [
                {"threshold": 0.5, "net_savings": 100.0}
            ]
            mock_cls.return_value = mock_svc

            resp = client.post(
                "/economics/threshold-sweep",
                json={
                    "start_time": "2024-01-01T00:00:00Z",
                    "end_time": "2024-12-31T23:59:59Z",
                    "thresholds": [0.3, 0.5, 0.7, 0.9],
                },
                headers=_auth_header(admin_token),
            )
            assert resp.status_code == 200


class TestLossCurve:
    def test_loss_curve_returns_200(self, client, admin_token):
        with patch(
            "src.api.routes.economics.FraudEconomicsService"
        ) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.compute_loss_curve.return_value = {"curve": []}
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/economics/loss-curve",
                params={
                    "start_time": "2024-01-01T00:00:00Z",
                    "end_time": "2024-12-31T23:59:59Z",
                },
                headers=_auth_header(admin_token),
            )
            assert resp.status_code == 200
