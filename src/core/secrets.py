"""
Secret management — unified interface for retrieving secrets from:

1. Environment variables (default, always available)
2. AWS Secrets Manager (when AWS_SECRETS_ARN is set)
3. HashiCorp Vault (when VAULT_ADDR is set)

On startup, secrets are fetched once and injected into the environment
so that pydantic-settings ``Settings`` can read them transparently.
"""
from __future__ import annotations

import json
import os
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)

_SENSITIVE_KEYS = frozenset({
    "SECRET_KEY",
    "DATABASE_URL",
    "DATABASE_URL_SYNC",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "SLACK_BOT_TOKEN",
    "GITHUB_TOKEN",
    "REDIS_URL",
})


def _load_aws_secrets(arn: str) -> dict[str, str]:
    """Fetch a JSON secret from AWS Secrets Manager."""
    try:
        import boto3
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=arn)
        secret_string = response.get("SecretString", "{}")
        secrets = json.loads(secret_string)
        logger.info("aws_secrets_loaded", arn=arn, keys=len(secrets))
        return secrets
    except ImportError:
        logger.warning("boto3_not_installed", msg="pip install boto3 to use AWS Secrets Manager")
        return {}
    except Exception as exc:
        logger.error("aws_secrets_error", error=str(exc))
        return {}


def _load_vault_secrets(addr: str, path: str, token: str | None) -> dict[str, str]:
    """Fetch secrets from HashiCorp Vault KV v2."""
    try:
        import httpx
        headers = {}
        if token:
            headers["X-Vault-Token"] = token
        url = f"{addr}/v1/{path}"
        resp = httpx.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        secrets = data.get("data", {}).get("data", {})
        logger.info("vault_secrets_loaded", path=path, keys=len(secrets))
        return secrets
    except ImportError:
        logger.warning("httpx_not_installed")
        return {}
    except Exception as exc:
        logger.error("vault_secrets_error", error=str(exc))
        return {}


def inject_secrets() -> None:
    """Load secrets from configured provider and inject into environment.

    Call this **before** ``get_settings()`` so pydantic-settings picks
    them up from the environment.  Existing env vars take precedence
    (secrets are only set if the env var is not already defined).
    """
    secrets: dict[str, str] = {}

    # AWS Secrets Manager
    aws_arn = os.environ.get("AWS_SECRETS_ARN")
    if aws_arn:
        secrets.update(_load_aws_secrets(aws_arn))

    # HashiCorp Vault
    vault_addr = os.environ.get("VAULT_ADDR")
    vault_path = os.environ.get("VAULT_SECRET_PATH", "secret/data/fraud-platform")
    vault_token = os.environ.get("VAULT_TOKEN")
    if vault_addr:
        secrets.update(_load_vault_secrets(vault_addr, vault_path, vault_token))

    injected = 0
    for key, value in secrets.items():
        upper_key = key.upper()
        if upper_key not in os.environ:
            os.environ[upper_key] = str(value)
            injected += 1

    if injected:
        logger.info("secrets_injected", count=injected)
    elif aws_arn or vault_addr:
        logger.info("secrets_already_present", msg="All secret env vars already set")


def mask_secret(value: str, visible_chars: int = 4) -> str:
    """Mask a secret value for safe logging. Shows first N chars."""
    if not value or len(value) <= visible_chars:
        return "****"
    return value[:visible_chars] + "*" * (len(value) - visible_chars)


def audit_secrets_present() -> dict[str, bool]:
    """Check which sensitive keys are present in the environment."""
    return {key: key in os.environ for key in sorted(_SENSITIVE_KEYS)}
