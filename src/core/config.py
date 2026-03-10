from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "fraud-detection-platform"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = "postgresql+asyncpg://fraud_user:fraud_pass@localhost:5432/fraud_db"
    database_url_sync: str = "postgresql://fraud_user:fraud_pass@localhost:5432/fraud_db"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_fraud_cases: str = "fraud_case_memory"
    qdrant_collection_merchant_patterns: str = "merchant_attack_patterns"
    qdrant_collection_investigator_notes: str = "investigator_notes"

    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: Optional[str] = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimension: int = 1536

    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-20250514"

    slack_bot_token: Optional[str] = None
    slack_fraud_ops_channel: str = "#fraud-ops-alerts"
    slack_model_alerts_channel: str = "#model-risk-alerts"

    github_token: Optional[str] = None
    github_repo: str = "org/fraud-rules-config"

    score_threshold_decline: float = 0.85
    score_threshold_review: float = 0.55
    score_threshold_stepup: float = 0.35

    feature_cache_ttl_seconds: int = 300
    feature_version: str = "v2.3.1"

    champion_model_version: str = "xgb-v4.2.0"
    shadow_model_versions: str = "lgb-v5.0.0-rc1"

    rate_limit_scoring_rps: int = 5000
    rate_limit_dashboard_rps: int = 100

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
