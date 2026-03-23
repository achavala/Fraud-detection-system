from __future__ import annotations

import time

import pytest
from fastapi import HTTPException
from jose import jwt

from src.api.middleware.auth import (
    create_access_token,
    require_role,
    ALGORITHM,
)
from src.core.config import get_settings


class TestAuthMiddleware:
    def test_create_token(self):
        """Create a token, verify it's a valid JWT string."""
        token = create_access_token(user_id="user-123", role="admin")
        assert isinstance(token, str)
        assert len(token) > 0
        parts = token.split(".")
        assert len(parts) == 3

    def test_token_contains_claims(self):
        """Decode token, verify user_id and role are present."""
        token = create_access_token(user_id="user-456", role="investigator")
        settings = get_settings()
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        assert payload["user_id"] == "user-456"
        assert payload["role"] == "investigator"
        assert "exp" in payload

    def test_expired_token(self):
        """Create token with past expiry, verify it fails validation."""
        settings = get_settings()
        exp = int(time.time()) - 3600  # 1 hour ago
        payload = {"user_id": "user-789", "role": "admin", "exp": exp}
        token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)

        with pytest.raises(Exception):
            jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])

    def test_role_check_allowed(self):
        """Verify role matching works."""
        checker = require_role("admin", "investigator")
        auth = {"user_id": "user-1", "role": "admin"}
        result = checker(auth)
        assert result == auth

        checker = require_role("readonly")
        auth = {"user_id": "user-2", "role": "readonly"}
        result = checker(auth)
        assert result == auth

    def test_role_check_denied(self):
        """Verify wrong role is rejected."""
        checker = require_role("admin")
        auth = {"user_id": "user-1", "role": "readonly"}
        with pytest.raises(HTTPException) as exc_info:
            checker(auth)
        assert exc_info.value.status_code == 403
