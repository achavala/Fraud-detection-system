"""
Model cards — structured metadata for each model version.
"""
from __future__ import annotations

import hashlib
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.models.audit import AuditEvent
from src.models.scoring import DimModelRegistry

MODEL_DIR = Path(__file__).parent.parent.parent.parent / "models_artifact"


class ModelCardService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    def _load_artifact(self, model_version: str) -> dict | None:
        """Load model artifact from models_artifact/{version}.pkl."""
        artifact_path = MODEL_DIR / f"{model_version}.pkl"
        if not artifact_path.exists():
            return None
        with open(artifact_path, "rb") as f:
            return pickle.load(f)

    def _model_type_from_version(self, model_version: str) -> str:
        """Derive model_type from version prefix."""
        v = model_version.lower()
        if v.startswith("xgb"):
            return "xgboost"
        if v.startswith("lgb"):
            return "lightgbm"
        return "unknown"

    def _compute_model_hash(self, model_version: str) -> str | None:
        """Compute SHA256 of the .pkl file."""
        artifact_path = MODEL_DIR / f"{model_version}.pkl"
        if not artifact_path.exists():
            return None
        h = hashlib.sha256()
        with open(artifact_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    async def generate_model_card(self, model_version: str) -> dict:
        """Load model artifact, query dim_model_registry, and return a complete model card."""
        artifact = self._load_artifact(model_version)
        if not artifact:
            raise FileNotFoundError(f"Model artifact not found: {model_version}.pkl")

        trained_at_str = artifact.get("trained_at")
        trained_at = None
        if trained_at_str:
            try:
                trained_at = datetime.fromisoformat(
                    trained_at_str.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        training_window = {"start": None, "end": None}
        if trained_at:
            start = trained_at - timedelta(days=180)
            training_window = {
                "start": start.date().isoformat(),
                "end": trained_at.date().isoformat(),
            }

        registry = None
        result = await self.db.execute(
            select(DimModelRegistry).where(
                DimModelRegistry.model_version == model_version
            )
        )
        registry = result.scalar_one_or_none()

        threshold_set = {
            "decline": float(self.settings.score_threshold_decline),
            "review": float(self.settings.score_threshold_review),
            "stepup": float(self.settings.score_threshold_stepup),
        }
        if registry:
            if registry.threshold_decline is not None:
                threshold_set["decline"] = float(registry.threshold_decline)
            if registry.threshold_review is not None:
                threshold_set["review"] = float(registry.threshold_review)
            if registry.threshold_stepup is not None:
                threshold_set["stepup"] = float(registry.threshold_stepup)

        training_metrics = artifact.get("training_metrics") or {}
        performance = {
            "auc_roc": training_metrics.get("auc_roc"),
            "auc_pr": training_metrics.get("auc_pr"),
            "precision": training_metrics.get("precision"),
            "recall": training_metrics.get("recall"),
            "f1": training_metrics.get("f1"),
            "tp": training_metrics.get("tp"),
            "fp": training_metrics.get("fp"),
            "fn": training_metrics.get("fn"),
            "tn": training_metrics.get("tn"),
        }

        feature_importances = artifact.get("feature_importances") or {}
        top_importances = sorted(
            feature_importances.items(), key=lambda x: x[1], reverse=True
        )[:10]

        promotion_history: list[dict] = []
        audit_result = await self.db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == "model",
                AuditEvent.entity_id == model_version,
            )
            .order_by(AuditEvent.created_at.asc())
        )
        for evt in audit_result.scalars().all():
            promotion_history.append({
                "event_type": evt.event_type,
                "created_at": evt.created_at.isoformat() if evt.created_at else None,
                "payload": evt.payload_json or {},
            })

        deployed_at = None
        approved_by = None
        for evt in reversed(list(promotion_history)):
            if evt.get("event_type") == "model_promoted":
                approved_by = (evt.get("payload") or {}).get("approved_by")
                deployed_at = evt.get("created_at")
                break

        feature_columns = artifact.get("feature_columns") or []
        if len(feature_columns) != 19:
            feature_columns = list(self._default_feature_columns())

        known_limitations = [
            "Trained on synthetic data",
            "Limited international merchant coverage",
            "Performance may degrade on novel fraud patterns",
        ]

        return {
            "model_version": model_version,
            "model_type": self._model_type_from_version(model_version),
            "training_window": training_window,
            "dataset_version": artifact.get("dataset_version", "simulation-v1.0"),
            "feature_version": getattr(
                registry, "feature_version", None
            ) or self.settings.feature_version,
            "feature_count": 19,
            "feature_columns": feature_columns,
            "performance": performance,
            "performance_by_segment": {
                "all": performance,
                "card_present": {},
                "card_not_present": {},
                "high_value": {},
                "international": {},
            },
            "calibration_method": "isotonic",
            "threshold_set": threshold_set,
            "known_limitations": known_limitations,
            "feature_importances": dict(top_importances),
            "promotion_history": promotion_history,
            "trained_at": trained_at_str,
            "deployed_at": deployed_at,
            "approved_by": approved_by,
            "model_hash": self._compute_model_hash(model_version),
        }

    def _default_feature_columns(self) -> list[str]:
        return [
            "customer_txn_count_1h",
            "customer_txn_count_24h",
            "customer_spend_24h",
            "card_txn_count_10m",
            "merchant_txn_count_10m",
            "merchant_chargeback_rate_30d",
            "device_txn_count_1d",
            "device_account_count_30d",
            "ip_account_count_7d",
            "ip_card_count_7d",
            "geo_distance_from_home_km",
            "geo_distance_from_last_txn_km",
            "seconds_since_last_txn",
            "amount_vs_customer_p95_ratio",
            "amount_vs_merchant_p95_ratio",
            "proxy_vpn_tor_flag",
            "device_risk_score",
            "behavioral_risk_score",
            "graph_cluster_risk_score",
        ]

    def list_model_cards(self) -> list[dict]:
        """List cards for all versions in models_artifact/."""
        if not MODEL_DIR.exists():
            return []
        cards: list[dict] = []
        for p in MODEL_DIR.glob("*.pkl"):
            version = p.stem
            try:
                card = {
                    "model_version": version,
                    "model_type": self._model_type_from_version(version),
                    "artifact_exists": True,
                }
                cards.append(card)
            except Exception:
                cards.append({
                    "model_version": version,
                    "model_type": "unknown",
                    "artifact_exists": True,
                })
        return sorted(cards, key=lambda c: c["model_version"])

    async def compare_model_cards(
        self, version_a: str, version_b: str
    ) -> dict:
        """Side-by-side comparison of two model cards."""
        card_a = await self.generate_model_card(version_a)
        card_b = await self.generate_model_card(version_b)

        def _diff(key: str, a: Any, b: Any) -> dict:
            return {"key": key, "version_a": a, "version_b": b}

        diffs: list[dict] = []
        for key in card_a:
            if key in card_b:
                va, vb = card_a[key], card_b[key]
                if va != vb:
                    diffs.append(_diff(key, va, vb))

        return {
            "version_a": version_a,
            "version_b": version_b,
            "card_a": card_a,
            "card_b": card_b,
            "diffs": diffs,
        }
