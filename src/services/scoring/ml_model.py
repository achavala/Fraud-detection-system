"""
ML model scorer — supports champion/challenger/shadow modes.
In production, this loads serialized models; here we provide a calibrated
heuristic scorer that demonstrates the full interface.
"""
from __future__ import annotations

import time
import math
import hashlib
from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.logging import get_logger
from src.models.scoring import FactModelScore, DimModelRegistry

logger = get_logger(__name__)


class FraudModelScorer:
    """
    Production interface for fraud model scoring.
    Wraps model loading, prediction, calibration, reason code generation,
    and SHAP value computation.
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

        raw_prob = self._predict(features, version)
        calibrated = self._calibrate(raw_prob, version)
        predicted_label = calibrated >= self.settings.score_threshold_review
        risk_band = self._compute_risk_band(calibrated)
        reason_codes = self._generate_reason_codes(features, calibrated)
        shap_values = self._compute_shap(features) if include_shap else None

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
        )
        return score_record

    async def score_shadow(
        self,
        auth_event_id: int,
        features: dict[str, Any],
    ) -> list[FactModelScore]:
        """Run all shadow models in parallel (logged, not acted upon)."""
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

    def _predict(self, features: dict, model_version: str) -> float:
        """
        Heuristic fraud probability scorer.
        In production, this calls a loaded XGBoost/LightGBM model.
        """
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
        score = max(0.01, min(0.99, score + noise))
        return score

    def _calibrate(self, raw: float, model_version: str) -> float:
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
        if not codes:
            codes.append("BASELINE_RISK")
        return codes[:5]

    def _compute_shap(self, features: dict) -> dict[str, float]:
        return {k: float(v) * 0.1 if v else 0.0 for k, v in features.items()}
