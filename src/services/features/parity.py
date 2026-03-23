"""
Feature parity validation suite — compare online vs offline features
to detect training/serving skew and drift.
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.models.features import FactTransactionFeaturesOnline, FactTransactionFeaturesOffline

# 19 feature names matching FactTransactionFeaturesOnline columns
FEATURE_NAMES = [
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

# Offline feature_json may use different keys; map our 19 names to possible keys
FEATURE_JSON_KEYS: dict[str, list[str]] = {
    "customer_txn_count_1h": ["customer_txn_count_1h"],
    "customer_txn_count_24h": ["customer_txn_count_24h"],
    "customer_spend_24h": ["customer_spend_24h"],
    "card_txn_count_10m": ["card_txn_count_10m"],
    "merchant_txn_count_10m": ["merchant_txn_count_10m"],
    "merchant_chargeback_rate_30d": ["merchant_chargeback_rate_30d"],
    "device_txn_count_1d": ["device_txn_count_1d"],
    "device_account_count_30d": ["device_account_count_30d"],
    "ip_account_count_7d": ["ip_account_count_7d"],
    "ip_card_count_7d": ["ip_card_count_7d"],
    "geo_distance_from_home_km": ["geo_distance_from_home_km", "distance_from_home_km"],
    "geo_distance_from_last_txn_km": ["geo_distance_from_last_txn_km", "distance_from_last_txn_km"],
    "seconds_since_last_txn": ["seconds_since_last_txn"],
    "amount_vs_customer_p95_ratio": ["amount_vs_customer_p95_ratio", "vs_customer_p95"],
    "amount_vs_merchant_p95_ratio": ["amount_vs_merchant_p95_ratio", "vs_merchant_p95"],
    "proxy_vpn_tor_flag": ["proxy_vpn_tor_flag"],
    "device_risk_score": ["device_risk_score", "risk_score"],
    "behavioral_risk_score": ["behavioral_risk_score"],
    "graph_cluster_risk_score": ["graph_cluster_risk_score"],
}

FEATURE_REGISTRY = {
    "features": [
        {"name": "customer_txn_count_1h", "type": "int", "range": [0, None], "description": "Customer transactions in last 1 hour"},
        {"name": "customer_txn_count_24h", "type": "int", "range": [0, None], "description": "Customer transactions in last 24 hours"},
        {"name": "customer_spend_24h", "type": "float", "range": [0, None], "description": "Customer total spend in last 24 hours"},
        {"name": "card_txn_count_10m", "type": "int", "range": [0, None], "description": "Card transactions in last 10 minutes"},
        {"name": "merchant_txn_count_10m", "type": "int", "range": [0, None], "description": "Merchant transactions in last 10 minutes"},
        {"name": "merchant_chargeback_rate_30d", "type": "float", "range": [0, 1], "description": "Merchant chargeback rate in last 30 days"},
        {"name": "device_txn_count_1d", "type": "int", "range": [0, None], "description": "Device transactions in last day"},
        {"name": "device_account_count_30d", "type": "int", "range": [0, None], "description": "Unique accounts on device in 30 days"},
        {"name": "ip_account_count_7d", "type": "int", "range": [0, None], "description": "Unique accounts on IP in 7 days"},
        {"name": "ip_card_count_7d", "type": "int", "range": [0, None], "description": "Unique cards on IP in 7 days"},
        {"name": "geo_distance_from_home_km", "type": "float", "range": [0, None], "description": "Distance from home in km"},
        {"name": "geo_distance_from_last_txn_km", "type": "float", "range": [0, None], "description": "Distance from last txn in km"},
        {"name": "seconds_since_last_txn", "type": "int", "range": [0, None], "description": "Seconds since customer last transaction"},
        {"name": "amount_vs_customer_p95_ratio", "type": "float", "range": [0, None], "description": "Amount vs customer p95 ratio"},
        {"name": "amount_vs_merchant_p95_ratio", "type": "float", "range": [0, None], "description": "Amount vs merchant p95 ratio"},
        {"name": "proxy_vpn_tor_flag", "type": "bool", "range": [0, 1], "description": "IP is proxy/VPN/Tor"},
        {"name": "device_risk_score", "type": "float", "range": [0, 1], "description": "Device risk score"},
        {"name": "behavioral_risk_score", "type": "float", "range": [0, 1], "description": "Behavioral risk score"},
        {"name": "graph_cluster_risk_score", "type": "float", "range": [0, 1], "description": "Graph cluster risk score"},
    ],
}


def _normalize(v: Any) -> float | int | bool:
    """Normalize value for comparison."""
    if v is None:
        return 0
    if isinstance(v, bool):
        return 1 if v else 0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0


def _extract_online_features(row: FactTransactionFeaturesOnline) -> dict[str, float | int]:
    """Extract feature dict from online row."""
    return {
        "customer_txn_count_1h": row.customer_txn_count_1h or 0,
        "customer_txn_count_24h": row.customer_txn_count_24h or 0,
        "customer_spend_24h": float(row.customer_spend_24h or 0),
        "card_txn_count_10m": row.card_txn_count_10m or 0,
        "merchant_txn_count_10m": row.merchant_txn_count_10m or 0,
        "merchant_chargeback_rate_30d": float(row.merchant_chargeback_rate_30d or 0),
        "device_txn_count_1d": row.device_txn_count_1d or 0,
        "device_account_count_30d": row.device_account_count_30d or 0,
        "ip_account_count_7d": row.ip_account_count_7d or 0,
        "ip_card_count_7d": row.ip_card_count_7d or 0,
        "geo_distance_from_home_km": float(row.geo_distance_from_home_km or 0),
        "geo_distance_from_last_txn_km": float(row.geo_distance_from_last_txn_km or 0),
        "seconds_since_last_txn": row.seconds_since_last_txn or 0,
        "amount_vs_customer_p95_ratio": float(row.amount_vs_customer_p95_ratio or 0),
        "amount_vs_merchant_p95_ratio": float(row.amount_vs_merchant_p95_ratio or 0),
        "proxy_vpn_tor_flag": 1 if row.proxy_vpn_tor_flag else 0,
        "device_risk_score": float(row.device_risk_score or 0),
        "behavioral_risk_score": float(row.behavioral_risk_score or 0),
        "graph_cluster_risk_score": float(row.graph_cluster_risk_score or 0),
    }


def _extract_offline_features(row: FactTransactionFeaturesOffline) -> dict[str, float | int]:
    """Extract feature dict from offline row (feature_json)."""
    fj = row.feature_json or {}
    result: dict[str, float | int] = {}
    for name in FEATURE_NAMES:
        keys = FEATURE_JSON_KEYS.get(name, [name])
        val = None
        for k in keys:
            if k in fj:
                val = fj[k]
                break
        if val is None:
            result[name] = 0
        elif isinstance(val, bool):
            result[name] = 1 if val else 0
        else:
            try:
                result[name] = float(val)
            except (TypeError, ValueError):
                result[name] = 0
    return result


def _schema_checksum() -> str:
    """Hash of feature definitions for contract versioning."""
    blob = json.dumps(FEATURE_REGISTRY, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


class FeatureParityValidator:
    """
    Compare online vs offline features to detect training/serving skew.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def validate_single(
        self,
        auth_event_id: int,
        tolerance: float = 0.01,
    ) -> dict:
        """
        Compare online vs offline features for a single event.
        Returns pass/fail with details: matching, mismatched (with deltas), missing.
        """
        online_result = await self.db.execute(
            select(FactTransactionFeaturesOnline).where(
                FactTransactionFeaturesOnline.auth_event_id == auth_event_id
            )
        )
        online_row = online_result.scalar_one_or_none()
        if not online_row:
            return {
                "pass": False,
                "auth_event_id": auth_event_id,
                "error": "online_features_not_found",
                "matching": [],
                "mismatched": [],
                "missing": FEATURE_NAMES,
            }

        feature_version = online_row.feature_version
        offline_result = await self.db.execute(
            select(FactTransactionFeaturesOffline).where(
                FactTransactionFeaturesOffline.auth_event_id == auth_event_id,
                FactTransactionFeaturesOffline.feature_version == feature_version,
            )
        )
        offline_row = offline_result.scalar_one_or_none()
        if not offline_row:
            return {
                "pass": False,
                "auth_event_id": auth_event_id,
                "error": "offline_features_not_found",
                "feature_version": feature_version,
                "matching": [],
                "mismatched": [],
                "missing": FEATURE_NAMES,
            }

        online_feats = _extract_online_features(online_row)
        offline_feats = _extract_offline_features(offline_row)

        matching: list[str] = []
        mismatched: list[dict] = []
        missing: list[str] = []

        for name in FEATURE_NAMES:
            on_val = _normalize(online_feats.get(name, 0))
            off_val = _normalize(offline_feats.get(name, 0))
            if name not in offline_feats and name not in (offline_row.feature_json or {}):
                missing.append(name)
                continue
            delta = abs(float(on_val) - float(off_val))
            if delta <= tolerance:
                matching.append(name)
            else:
                mismatched.append({
                    "feature": name,
                    "online": on_val,
                    "offline": off_val,
                    "delta": delta,
                })

        passed = len(mismatched) == 0 and len(missing) == 0
        return {
            "pass": passed,
            "auth_event_id": auth_event_id,
            "feature_version": feature_version,
            "tolerance": tolerance,
            "matching": matching,
            "mismatched": mismatched,
            "missing": missing,
        }

    async def validate_batch(
        self,
        auth_event_ids: list[int],
        tolerance: float = 0.01,
    ) -> dict:
        """
        Batch validation: run validate_single for each, aggregate results.
        """
        results = []
        pass_count = 0
        fail_count = 0
        feature_drift: dict[str, list[float]] = {n: [] for n in FEATURE_NAMES}

        for aid in auth_event_ids:
            r = await self.validate_single(aid, tolerance)
            results.append(r)
            if r.get("pass"):
                pass_count += 1
            else:
                fail_count += 1
            for m in r.get("mismatched", []):
                feat = m.get("feature", "")
                if feat in feature_drift:
                    feature_drift[feat].append(m.get("delta", 0))

        worst_mismatches: list[dict] = []
        for r in results:
            for m in r.get("mismatched", []):
                worst_mismatches.append({
                    "auth_event_id": r.get("auth_event_id"),
                    **m,
                })
        worst_mismatches.sort(key=lambda x: x.get("delta", 0), reverse=True)
        worst_mismatches = worst_mismatches[:20]

        feature_summary = {}
        for name, deltas in feature_drift.items():
            if deltas:
                feature_summary[name] = {
                    "count_mismatched": len(deltas),
                    "mean_abs_error": sum(deltas) / len(deltas),
                    "max_error": max(deltas),
                }

        return {
            "total_checked": len(auth_event_ids),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "worst_mismatches": worst_mismatches,
            "feature_level_summary": feature_summary,
            "results": results,
        }

    async def generate_parity_report(
        self,
        sample_size: int = 1000,
        tolerance: float = 0.01,
    ) -> dict:
        """
        Full report: sample random auth_event_ids with both online and offline features,
        run validate_batch, compute per-feature statistics.
        """
        # Find auth_event_ids that have BOTH online and offline features
        subq = (
            select(FactTransactionFeaturesOnline.auth_event_id)
            .join(
                FactTransactionFeaturesOffline,
                and_(
                    FactTransactionFeaturesOnline.auth_event_id == FactTransactionFeaturesOffline.auth_event_id,
                    FactTransactionFeaturesOnline.feature_version == FactTransactionFeaturesOffline.feature_version,
                )
            )
        )
        result = await self.db.execute(subq)
        all_ids = [r[0] for r in result.fetchall()]
        if not all_ids:
            return {
                "pass": False,
                "error": "no_matching_records",
                "sample_size": 0,
                "total_available": 0,
                "per_feature_stats": {},
                "aggregate": {},
            }

        sample_ids = random.sample(all_ids, min(sample_size, len(all_ids)))
        batch_result = await self.validate_batch(sample_ids, tolerance)

        # Per-feature statistics
        per_feature: dict[str, dict] = {}
        for name in FEATURE_NAMES:
            summary = batch_result.get("feature_level_summary", {}).get(name, {})
            deltas = summary.get("count_mismatched", 0)
            mae = summary.get("mean_abs_error", 0)
            max_err = summary.get("max_error", 0)
            per_feature[name] = {
                "mean_absolute_error": mae,
                "max_error": max_err,
                "mismatch_count": deltas,
                "correlation": None,  # Would need raw values for correlation
            }

        pass_count = batch_result.get("pass_count", 0)
        total = batch_result.get("total_checked", 0)
        passed = total > 0 and pass_count == total

        return {
            "pass": passed,
            "sample_size": len(sample_ids),
            "total_available": len(all_ids),
            "pass_count": pass_count,
            "fail_count": batch_result.get("fail_count", 0),
            "per_feature_stats": per_feature,
            "aggregate": {
                "total_checked": total,
                "pass_rate": pass_count / total if total > 0 else 0,
            },
            "worst_mismatches": batch_result.get("worst_mismatches", [])[:10],
        }

    def get_feature_registry(self) -> dict:
        """
        Returns the feature contract: 19 feature names, types, ranges, descriptions,
        current feature version, schema checksum.
        """
        return {
            **FEATURE_REGISTRY,
            "feature_version": self.settings.feature_version,
            "schema_checksum": _schema_checksum(),
            "feature_count": len(FEATURE_NAMES),
        }
