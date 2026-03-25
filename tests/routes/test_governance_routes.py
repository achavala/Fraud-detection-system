"""
HTTP route tests for /governance and /model endpoints.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
def model_risk_token():
    return create_access_token("test-mr", "model_risk")


@pytest.fixture
def readonly_token():
    return create_access_token("test-reader", "readonly")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


_GOV_SVC = "src.api.routes.model.ModelGovernanceService"
_CARD_SVC = "src.api.routes.governance.ModelCardService"
_CONTRACT = "src.api.routes.governance.ContractRegistry"


class TestModelRegister:
    def test_register_requires_auth(self, client):
        resp = client.post("/model/register", json={
            "model_version": "test-v1",
            "model_family": "xgboost",
            "model_type": "binary_classifier",
            "feature_version": "v1",
            "threshold_decline": 0.85,
            "threshold_review": 0.55,
            "threshold_stepup": 0.35,
            "owner": "test",
        })
        assert resp.status_code in (401, 403)

    def test_register_with_admin(self, client, admin_token):
        with patch(_GOV_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_model = MagicMock()
            mock_model.model_version = "test-v1"
            mock_model.deployment_status = "shadow"
            mock_svc.register_model.return_value = mock_model
            mock_cls.return_value = mock_svc

            resp = client.post(
                "/model/register",
                json={
                    "model_version": "test-v1",
                    "model_family": "xgboost",
                    "model_type": "binary_classifier",
                    "feature_version": "v1",
                    "threshold_decline": 0.85,
                    "threshold_review": 0.55,
                    "threshold_stepup": 0.35,
                    "owner": "test",
                },
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
            assert resp.json()["model_version"] == "test-v1"


class TestModelPromote:
    def test_promote_requires_admin(self, client, model_risk_token):
        resp = client.post(
            "/model/promote",
            params={
                "model_version": "v1",
                "approved_by": "boss",
                "reason": "better",
            },
            headers=_auth(model_risk_token),
        )
        assert resp.status_code == 403

    def test_promote_with_admin(self, client, admin_token):
        with patch(_GOV_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_model = MagicMock()
            mock_model.model_version = "v1"
            mock_model.deployment_status = "champion"
            mock_svc.promote_model.return_value = mock_model
            mock_cls.return_value = mock_svc

            resp = client.post(
                "/model/promote",
                params={
                    "model_version": "v1",
                    "approved_by": "boss",
                    "reason": "better",
                },
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200


class TestModelHealth:
    def test_health_no_auth_needed(self, client, admin_token):
        with patch(_GOV_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.get_model_health.return_value = {"status": "healthy"}
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/model/health/xgb-v4.2.0",
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200


class TestGovernanceModelCard:
    def test_model_card_requires_auth(self, client):
        resp = client.get("/governance/model-card/xgb-v4.2.0")
        assert resp.status_code in (401, 403)

    def test_model_card_with_readonly(self, client, readonly_token):
        with patch(_CARD_SVC) as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.generate_model_card.return_value = {"version": "xgb-v4.2.0"}
            mock_cls.return_value = mock_svc

            resp = client.get(
                "/governance/model-card/xgb-v4.2.0",
                headers=_auth(readonly_token),
            )
            assert resp.status_code == 200


class TestGovernanceContracts:
    def test_list_contracts(self, client, admin_token):
        with patch(_CONTRACT) as mock_reg:
            mock_reg.get_all_contracts.return_value = {"auth_event": MagicMock()}
            mock_reg.get_all_contracts.return_value["auth_event"].model_json_schema.return_value = {}

            resp = client.get(
                "/governance/contracts",
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
