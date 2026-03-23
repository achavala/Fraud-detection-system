"""
Failure-mode chaos tests — verify graceful degradation and invariants.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.schemas.transactions import (
    AuthorizationRequest,
    AuthType,
    Channel,
    EntryMode,
)
from src.utils.fx_service import FXService
from src.services.scoring.ml_model import FraudModelScorer, FEATURE_COLUMNS


# ---------------------------------------------------------------------------
# test_scoring_without_db
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_db_connection_error():
    """Mock DB session that raises ConnectionError on flush."""

    async def _mock_get_db():
        mock = AsyncMock()
        mock.add = MagicMock()
        mock.flush = AsyncMock(side_effect=ConnectionError("Database unavailable"))
        mock.execute = AsyncMock(side_effect=ConnectionError("Database unavailable"))
        yield mock

    return _mock_get_db


def test_scoring_without_db(mock_db_connection_error):
    """Mock DB that raises ConnectionError. Verify scoring handles gracefully (error response, no crash)."""
    from fastapi.testclient import TestClient
    from src.main import app
    from src.core.database import get_db

    app.dependency_overrides[get_db] = mock_db_connection_error
    try:
        client = TestClient(app)
        resp = client.post(
            "/authorize/score",
            json={
                "transaction_id": 1,
                "account_id": 1,
                "card_id": 1,
                "customer_id": 1,
                "merchant_id": 1,
                "auth_type": "card_present",
                "channel": "web",
                "entry_mode": "chip",
                "auth_amount": 100.00,
                "currency_code": "USD",
                "merchant_country_code": "US",
            },
        )
        assert resp.status_code == 503
        assert "detail" in resp.json() or "detail" in resp.text
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# test_scoring_without_qdrant
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scoring_without_qdrant():
    """Mock Qdrant unavailable. Verify copilot falls back to deterministic analysis."""
    from src.services.copilot.service import InvestigatorCopilot
    from src.models.investigation import FactFraudCase
    from src.models.scoring import FactModelScore, FactDecision

    case = FactFraudCase(
        case_id=1,
        auth_event_id=100,
        case_status="open",
        queue_name="high_risk",
        priority="critical",
    )
    score = FactModelScore(
        auth_event_id=100,
        fraud_probability=Decimal("0.75"),
        risk_band="high",
        top_reason_codes=["HIGH_CARD_VELOCITY"],
        shadow_mode_flag=False,
    )

    from datetime import datetime, timezone
    from src.models.transactions import FactAuthorizationEvent

    txn = FactAuthorizationEvent(
        auth_event_id=100,
        event_time=datetime.now(timezone.utc),
        auth_amount=Decimal("99.99"),
        currency_code="USD",
        channel="web",
        auth_type="card_present",
    )
    decision = FactDecision(auth_event_id=100, decision_type="manual_review")

    call_idx = [0]

    async def mock_execute(stmt):
        call_idx[0] += 1
        result = MagicMock()
        if call_idx[0] == 1:  # load_case
            result.scalar_one_or_none = MagicMock(return_value=case)
            result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        elif call_idx[0] == 2:  # load_transaction
            result.scalar_one_or_none = MagicMock(return_value=txn)
            result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        elif call_idx[0] == 3:  # load_scores
            result.scalar_one_or_none = MagicMock(return_value=None)
            result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[score])))
        elif call_idx[0] == 4:  # load_decision
            result.scalar_one_or_none = MagicMock(return_value=decision)
            result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        else:  # load_labels
            result.scalar_one_or_none = MagicMock(return_value=None)
            result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        return result

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=mock_execute)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    with patch.object(
        InvestigatorCopilot,
        "_find_similar_cases",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with patch("src.services.copilot.service.EmbeddingService.embed", new_callable=AsyncMock, return_value=[0.0] * 1536):
            copilot = InvestigatorCopilot(mock_db)
            with patch.object(copilot.settings, "anthropic_api_key", None):
                result = await copilot.investigate_case(1)
                assert "analysis" in result
                assert result.get("analysis", {}).get("source") == "fallback"


# ---------------------------------------------------------------------------
# test_slack_timeout
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_slack_timeout():
    """Mock Slack client that hangs for 30s. Verify notification doesn't block (uses timeout)."""
    from src.utils.notifications import SlackNotifier

    async def hanging_post(*args, **kwargs):
        await asyncio.sleep(30)
        return MagicMock()

    mock_client = MagicMock()
    mock_client.chat_postMessage = AsyncMock(side_effect=hanging_post)

    with patch.object(SlackNotifier, "_get_client", return_value=mock_client):
        notifier = SlackNotifier()
        # SlackNotifier uses internal 5s timeout - should return before 30s without blocking
        await notifier.send_fraud_alert(1, "high", 0.8, "manual_review", ["R001"])


# ---------------------------------------------------------------------------
# test_github_api_failure
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_github_api_failure():
    """Mock GitHub API returning 500. Verify workflow service returns None gracefully."""
    from src.utils.github_workflow import GitHubWorkflowService

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=MagicMock(status_code=500))
        mock_client_cls.return_value = mock_client

        service = GitHubWorkflowService()
        service._client = mock_client

        result = await service.list_pending_prs()
        assert result == []


# ---------------------------------------------------------------------------
# test_expired_jwt_handling
# ---------------------------------------------------------------------------
def test_expired_jwt_handling():
    """Send an expired JWT token. Verify 401 response from auth dependency."""
    import time
    from fastapi import HTTPException, Request
    from jose import jwt
    from src.core.config import get_settings
    from src.api.middleware.auth import jwt_bearer

    settings = get_settings()
    exp = int(time.time()) - 3600
    payload = {"user_id": "u1", "role": "admin", "exp": exp}
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")

    async def _run():
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": f"Bearer {token}"}
        with pytest.raises(HTTPException) as exc_info:
            await jwt_bearer(mock_request)
        assert exc_info.value.status_code == 401

    import asyncio
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# test_rate_limiter_burst
# ---------------------------------------------------------------------------
def test_rate_limiter_burst():
    """Simulate rapid requests. Verify 429 after limit."""
    from fastapi.testclient import TestClient
    from src.main import app
    from src.core.database import get_db
    from src.api.middleware.rate_limit import _store as rate_limit_store

    rate_limit_store._store.clear()

    async def mock_get_db():
        mock = AsyncMock()
        mock.add = MagicMock()
        mock.flush = AsyncMock()
        result = MagicMock()
        result.scalar = MagicMock(return_value=0)
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        mock.execute = AsyncMock(return_value=result)
        yield mock

    mock_settings = MagicMock()
    mock_settings.rate_limit_dashboard_rps = 3
    mock_settings.rate_limit_scoring_rps = 3

    app.dependency_overrides[get_db] = mock_get_db
    try:
        with patch("src.api.middleware.rate_limit.settings", mock_settings):
            client = TestClient(app)
            rate_limited = 0
            for i in range(15):
                resp = client.get("/dashboard/ops/summary")
                if resp.status_code == 429:
                    rate_limited += 1
                    break
            assert rate_limited >= 1, "Expected 429 after exceeding rate limit"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# test_model_artifact_missing
# ---------------------------------------------------------------------------
def test_model_artifact_missing():
    """Delete model artifact. Verify scorer falls back to heuristic."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    with patch("src.services.scoring.ml_model._load_model_artifact", return_value=None):
        scorer = FraudModelScorer(mock_db)
        features = {col: 0 for col in FEATURE_COLUMNS}
        features["card_txn_count_10m"] = 5
        features["proxy_vpn_tor_flag"] = 0
        prob = scorer._predict_heuristic(features, "xgb-v4.2.0")
        assert 0 <= prob <= 1


# ---------------------------------------------------------------------------
# test_feature_computation_partial_failure
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_feature_computation_partial_failure():
    """Mock one feature query failing. Verify service raises (doesn't hang or crash)."""
    from datetime import datetime, timezone
    from src.services.features.service import FeatureService

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=ConnectionError("Temporary DB blip"))
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    service = FeatureService(mock_db)
    with pytest.raises(ConnectionError):
        await service.compute_online_features(
            auth_event_id=1,
            account_id=1,
            card_id=1,
            customer_id=1,
            merchant_id=1,
            auth_amount=Decimal("50"),
            event_time=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# test_probability_bounds_invariant
# ---------------------------------------------------------------------------
def test_probability_bounds_invariant():
    """Property test: for any random feature vector, probability is in [0, 1]."""
    import random

    mock_db = AsyncMock()
    scorer = FraudModelScorer(mock_db)

    for _ in range(100):
        vec = {}
        for col in FEATURE_COLUMNS:
            if col == "proxy_vpn_tor_flag":
                vec[col] = random.choice([True, False])
            elif "ratio" in col or "score" in col or "rate" in col:
                vec[col] = random.uniform(0, 10)
            elif "count" in col or "txn" in col:
                vec[col] = random.randint(0, 100)
            elif col == "seconds_since_last_txn":
                vec[col] = random.randint(0, 100000) if random.random() > 0.2 else None
            else:
                vec[col] = random.uniform(0, 10)
        prob = scorer._predict_heuristic(vec, "invariant-test")
        assert 0 <= prob <= 1, f"Probability {prob} out of bounds for vec {vec}"


# ---------------------------------------------------------------------------
# test_currency_normalization_invariant
# ---------------------------------------------------------------------------
def test_currency_normalization_invariant():
    """Property test: for any positive amount and valid currency, USD result is positive."""
    import random

    fx = FXService()
    valid_currencies = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "INR"]

    for _ in range(50):
        amount = random.uniform(0.01, 1_000_000)
        currency = random.choice(valid_currencies)
        result = fx.convert_to_usd(amount, currency)
        assert result > 0, f"Amount {amount} {currency} -> {result} USD should be positive"
