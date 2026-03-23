from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from src.core.config import get_settings

settings = get_settings()

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

SUPPORTED_ROLES = frozenset({"admin", "investigator", "model_risk", "readonly"})


class JWTBearer(HTTPBearer):
    """JWT authentication using HTTP Bearer scheme. Extracts user_id and role from token."""

    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request) -> dict[str, str]:
        credentials: HTTPAuthorizationCredentials | None = await super().__call__(request)
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.secret_key,
                algorithms=[ALGORITHM],
            )
            user_id = payload.get("user_id")
            role = payload.get("role")
            if not user_id or not role:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if role not in SUPPORTED_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Unsupported role: {role}",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return {"user_id": str(user_id), "role": role}
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e!s}",
                headers={"WWW-Authenticate": "Bearer"},
            )


jwt_bearer = JWTBearer()


def require_role(*allowed_roles: str):
    """Dependency factory that checks the user's role against allowed roles."""

    def _check_role(
        auth: Annotated[dict[str, str], Depends(jwt_bearer)],
    ) -> dict[str, str]:
        if auth["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {auth['role']} not authorized for this endpoint",
            )
        return auth

    return _check_role


def create_access_token(
    user_id: str,
    role: str,
    expiry_hours: float = ACCESS_TOKEN_EXPIRE_HOURS,
) -> str:
    """Create a JWT access token. For testing/development."""
    if role not in SUPPORTED_ROLES:
        raise ValueError(f"Unsupported role: {role}. Must be one of {SUPPORTED_ROLES}")
    expire = datetime.utcnow() + timedelta(hours=expiry_hours)
    payload = {"user_id": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
