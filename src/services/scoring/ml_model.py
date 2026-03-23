"""
ML model scorer — loads real XGBoost/LightGBM serialized models.
Supports champion/challenger/shadow modes with full SHAP explainability.
Falls back to calibrated heuristic when no model artifact is available.
"""
from __future__ import annotations

import os
import time
import math
import pickle
import hashlib
from datetime import datetime, timezone
from typing import Optional, Any
from pathlib import Path

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.logging import get_logger
from src.models.scoring import FactModelScore, DimModelRegistry

logger = get_logger(__name__)

MODEL_DIR = Path(__file__).parent.parent.parent.parent / "models_artifact"

FEATURE_COLUMNS = [
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

_model_cache: dict[str, dict] = {}


def _load_model_artifact(model_version: str) -> Optional[dict]:
    """Load a serialized model from disk with caching."""
    if model_version in _model_cache:
        return _model_cache[model_version]

    artifact_path = MODEL_DIR / f"{model_version}.pkl"
    if not artifact_path.exists():
        return None

    try:
        with open(artifact_path, "rb") as f:
            artifact = pickle.load(f)
        _model_cache[model_version] = artifact
        logger.info("model_loaded", model_version=model_version, path=str(artifact_path))
        return artifact
    except Exception as e:
        logger.warning("model_load_failed", model_version=model_version, error=str(e))
        return None


class FraudModelScorer:
    """
    Production interface for fraud model scoring.
    Loads real XGBoost/LightGBM models, runs prediction + calibration,
    generates SHAP explanations, and records all scores.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def score(
        self,
        auth_event_id: int,
        features: dict[str, Any],
        model_version: Optional[str] = None,
        shadow_mode: bool = False,
        include_shap: bool = False,
    ) -> FactModelScore:
        version = model_version or self.settings.champion_model_version
        start = time.monotonic()

        artifact = _load_model_artifact(version)
        if artifact:
            raw_prob, calibrated = self._predict_with_model(features, artifact)
        else:
            raw_prob = self._predict_heuristic(features, version)
            calibrated = self._calibrate_heuristic(raw_prob)

        predicted_label = calibrated >= self.settings.score_threshold_review
        risk_band = self._compute_risk_band(calibrated)
        reason_codes = self._generate_reason_codes(features, calibrated)

        shap_values = None
        if include_shap:
            shap_values = self._compute_shap(features, artifact)

        latency = int((time.monotonic() - start) * 1000)

        score_record = FactModelScore(
            auth_event_id=auth_event_id,
            model_version=version,
            score_time=datetime.now(timezone.utc),
            fraud_probability=raw_prob,
            calibrated_probability=calibrated,
            predicted_label=predicted_label,
            risk_band=risk_band,
            top_reason_codes=reason_codes,
            shap_values_json=shap_values,
            latency_ms=latency,
            shadow_mode_flag=shadow_mode,
        )
        self.db.add(score_record)
        await self.db.flush()

        logger.info(
            "model_scored",
            auth_event_id=auth_event_id,
            model_version=version,
            probability=float(calibrated),
            risk_band=risk_band,
            shadow=shadow_mode,
            latency_ms=latency,
            real_model=artifact is not None,
        )
        return score_record

    async def score_shadow(
        self,
        auth_event_id: int,
        features: dict[str, Any],
    ) -> list[FactModelScore]:
        """Run all shadow models (logged, not acted upon)."""
        shadow_versions = [
            v.strip()
            for v in self.settings.shadow_model_versions.split(",")
            if v.strip()
        ]
        results = []
        for version in shadow_versions:
            result = await self.score(
                auth_event_id=auth_event_id,
                features=features,
                model_version=version,
                shadow_mode=True,
            )
            results.append(result)
        return results

    def _predict_with_model(self, features: dict, artifact: dict) -> tuple:
        """Score using a real trained model artifact."""
        feature_cols = artifact.get("feature_columns", FEATURE_COLUMNS)
        x = np.array([[
            self._coerce_numeric(features.get(col, 0))
            for col in feature_cols
        ]])

        model = artifact["model"]
        proba = model.predict_proba(x)[0]
        calibrated_prob = float(proba[1])

        raw_model = artifact.get("raw_model")
        if raw_model and hasattr(raw_model, "predict_proba"):
            raw_proba = raw_model.predict_proba(x)[0]
            raw_prob = float(raw_proba[1])
        else:
            raw_prob = calibrated_prob

        return raw_prob, calibrated_prob

    def _predict_heuristic(self, features: dict, model_version: str) -> float:
        """Fallback heuristic when no model artifact exists."""
        score = 0.0
        weights = {
            "card_txn_count_10m": (0.12, 5),
            "device_account_count_30d": (0.15, 3),
            "ip_card_count_7d": (0.10, 5),
            "customer_txn_count_1h": (0.08, 10),
            "proxy_vpn_tor_flag": (0.12, 1),
            "device_risk_score": (0.10, 1),
            "amount_vs_customer_p95_ratio": (0.08, 3),
            "seconds_since_last_txn": (-0.05, 60),
            "graph_cluster_risk_score": (0.10, 1),
            "merchant_chargeback_rate_30d": (0.10, 0.05),
        }

        for feature, (weight, threshold) in weights.items():
            val = features.get(feature, 0)
            if val is None:
                continue
            if isinstance(val, bool):
                val = 1 if val else 0
            val = float(val)
            if weight < 0:
                contribution = weight * max(0, 1 - val / threshold) if threshold else 0
            else:
                contribution = weight * min(val / threshold, 1.0) if threshold else 0
            score += contribution

        noise = int(hashlib.md5(model_version.encode()).hexdigest()[:4], 16) / 65535 * 0.02
        return max(0.01, min(0.99, score + noise))

    def _calibrate_heuristic(self, raw: float) -> float:
        return 1.0 / (1.0 + math.exp(-5 * (raw - 0.5)))

    def _compute_risk_band(self, probability: float) -> str:
        if probability >= 0.85:
            return "critical"
        elif probability >= 0.65:
            return "high"
        elif probability >= 0.40:
            return "medium"
        elif probability >= 0.20:
            return "low"
        return "minimal"

    def _generate_reason_codes(self, features: dict, probability: float) -> list[str]:
        codes = []
        if features.get("card_txn_count_10m", 0) >= 5:
            codes.append("HIGH_CARD_VELOCITY")
        if features.get("device_account_count_30d", 0) >= 3:
            codes.append("MULTI_ACCOUNT_DEVICE")
        if features.get("ip_card_count_7d", 0) >= 5:
            codes.append("MULTI_CARD_IP")
        if features.get("proxy_vpn_tor_flag"):
            codes.append("VPN_PROXY_TOR")
        if features.get("amount_vs_customer_p95_ratio", 0) > 3:
            codes.append("UNUSUAL_AMOUNT")
        if (features.get("seconds_since_last_txn") or 999999) < 30:
            codes.append("RAPID_FIRE")
        if features.get("device_risk_score", 0) >= 0.4:
            codes.append("RISKY_DEVICE")
        if features.get("graph_cluster_risk_score", 0) > 0.5:
            codes.append("FRAUD_RING_PROXIMITY")
        if features.get("geo_distance_from_home_km", 0) and features["geo_distance_from_home_km"] > 5000:
            codes.append("GEO_ANOMALY")
        if features.get("merchant_chargeback_rate_30d", 0) > 0.05:
            codes.append("HIGH_RISK_MERCHANT")
        if not codes:
            codes.append("BASELINE_RISK")
        return codes[:5]

    def _compute_shap(self, features: dict, artifact: Optional[dict] = None) -> dict[str, float]:
        """Compute real SHAP values if model loaded, else feature-importance approximation."""
        if artifact and artifact.get("raw_model"):
            try:
                import shap
                raw_model = artifact["raw_model"]
                feature_cols = artifact.get("feature_columns", FEATURE_COLUMNS)
                x = np.array([[
                    self._coerce_numeric(features.get(col, 0))
                    for col in feature_cols
                ]])
                explainer = shap.TreeExplainer(raw_model)
                shap_values = explainer.shap_values(x)
                if isinstance(shap_values, list):
                    shap_values = shap_values[1]
                return dict(zip(feature_cols, [float(v) for v in shap_values[0]]))
            except Exception as e:
                logger.warning("shap_computation_failed", error=str(e))

        if artifact and artifact.get("feature_importances"):
            importances = artifact["feature_importances"]
            return {
                k: float(importances.get(k, 0)) * self._coerce_numeric(features.get(k, 0))
                for k in FEATURE_COLUMNS
            }

        return {k: self._coerce_numeric(features.get(k, 0)) * 0.1 for k in FEATURE_COLUMNS}

    def _coerce_numeric(self, v) -> float:
        if v is None:
            return 0.0
        if isinstance(v, bool):
            return 1.0 if v else 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
