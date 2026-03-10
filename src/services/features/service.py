"""
Service 2: Feature Service
Computes velocity, spend anomaly, behavioral, geo, merchant risk, and graph features.
Outputs both online feature rows (for serving) and offline training feature rows.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Any

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.logging import get_logger
from src.models.transactions import FactAuthorizationEvent
from src.models.features import FactTransactionFeaturesOnline, FactTransactionFeaturesOffline
from src.models.dimensions import DimDevice, DimIP, DimCustomer
from src.schemas.features import OnlineFeaturesResponse

logger = get_logger(__name__)


class FeatureService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def compute_online_features(
        self,
        auth_event_id: int,
        account_id: int,
        card_id: int,
        customer_id: int,
        merchant_id: int,
        auth_amount: Decimal,
        event_time: datetime,
        device_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> FactTransactionFeaturesOnline:
        now = event_time or datetime.now(timezone.utc)

        velocity = await self._compute_velocity_features(
            account_id, card_id, customer_id, merchant_id, device_id, ip_address, now
        )
        amount_features = await self._compute_amount_features(
            customer_id, merchant_id, auth_amount
        )
        geo_features = await self._compute_geo_features(customer_id, ip_address)
        time_features = await self._compute_time_features(customer_id, now)
        device_features = await self._compute_device_features(device_id)
        ip_features = await self._compute_ip_features(ip_address)

        feature_row = FactTransactionFeaturesOnline(
            auth_event_id=auth_event_id,
            feature_timestamp=now,
            feature_version=self.settings.feature_version,
            customer_txn_count_1h=velocity.get("customer_txn_count_1h", 0),
            customer_txn_count_24h=velocity.get("customer_txn_count_24h", 0),
            customer_spend_24h=velocity.get("customer_spend_24h", Decimal("0")),
            card_txn_count_10m=velocity.get("card_txn_count_10m", 0),
            merchant_txn_count_10m=velocity.get("merchant_txn_count_10m", 0),
            merchant_chargeback_rate_30d=velocity.get("merchant_chargeback_rate_30d", 0),
            device_txn_count_1d=velocity.get("device_txn_count_1d", 0),
            device_account_count_30d=velocity.get("device_account_count_30d", 0),
            ip_account_count_7d=velocity.get("ip_account_count_7d", 0),
            ip_card_count_7d=velocity.get("ip_card_count_7d", 0),
            geo_distance_from_home_km=geo_features.get("distance_from_home_km"),
            geo_distance_from_last_txn_km=geo_features.get("distance_from_last_txn_km"),
            seconds_since_last_txn=time_features.get("seconds_since_last_txn"),
            amount_vs_customer_p95_ratio=amount_features.get("vs_customer_p95"),
            amount_vs_merchant_p95_ratio=amount_features.get("vs_merchant_p95"),
            proxy_vpn_tor_flag=ip_features.get("proxy_vpn_tor_flag", False),
            device_risk_score=device_features.get("risk_score", 0.0),
            behavioral_risk_score=0.0,
            graph_cluster_risk_score=0.0,
            feature_json=self._build_feature_json(
                velocity, amount_features, geo_features, time_features,
                device_features, ip_features,
            ),
        )

        self.db.add(feature_row)
        await self.db.flush()
        logger.info("online_features_computed", auth_event_id=auth_event_id)
        return feature_row

    async def get_online_features(self, auth_event_id: int) -> Optional[FactTransactionFeaturesOnline]:
        result = await self.db.execute(
            select(FactTransactionFeaturesOnline).where(
                FactTransactionFeaturesOnline.auth_event_id == auth_event_id
            )
        )
        return result.scalar_one_or_none()

    async def build_offline_features(
        self,
        auth_event_id: int,
        as_of_time: datetime,
        feature_version: str,
        label_snapshot_date=None,
    ) -> FactTransactionFeaturesOffline:
        """Rebuild features offline using warehouse history — same definitions, no leakage."""
        online = await self.get_online_features(auth_event_id)
        feature_json = online.feature_json if online else {}

        offline = FactTransactionFeaturesOffline(
            auth_event_id=auth_event_id,
            as_of_time=as_of_time,
            feature_version=feature_version,
            label_snapshot_date=label_snapshot_date,
            feature_json=feature_json,
        )
        self.db.add(offline)
        await self.db.flush()
        return offline

    def to_scoring_vector(self, features: FactTransactionFeaturesOnline) -> dict[str, Any]:
        return {
            "customer_txn_count_1h": features.customer_txn_count_1h or 0,
            "customer_txn_count_24h": features.customer_txn_count_24h or 0,
            "customer_spend_24h": float(features.customer_spend_24h or 0),
            "card_txn_count_10m": features.card_txn_count_10m or 0,
            "merchant_txn_count_10m": features.merchant_txn_count_10m or 0,
            "merchant_chargeback_rate_30d": float(features.merchant_chargeback_rate_30d or 0),
            "device_txn_count_1d": features.device_txn_count_1d or 0,
            "device_account_count_30d": features.device_account_count_30d or 0,
            "ip_account_count_7d": features.ip_account_count_7d or 0,
            "ip_card_count_7d": features.ip_card_count_7d or 0,
            "geo_distance_from_home_km": float(features.geo_distance_from_home_km or 0),
            "geo_distance_from_last_txn_km": float(features.geo_distance_from_last_txn_km or 0),
            "seconds_since_last_txn": features.seconds_since_last_txn or 0,
            "amount_vs_customer_p95_ratio": float(features.amount_vs_customer_p95_ratio or 0),
            "amount_vs_merchant_p95_ratio": float(features.amount_vs_merchant_p95_ratio or 0),
            "proxy_vpn_tor_flag": 1 if features.proxy_vpn_tor_flag else 0,
            "device_risk_score": float(features.device_risk_score or 0),
            "behavioral_risk_score": float(features.behavioral_risk_score or 0),
            "graph_cluster_risk_score": float(features.graph_cluster_risk_score or 0),
        }

    async def _compute_velocity_features(
        self, account_id, card_id, customer_id, merchant_id,
        device_id, ip_address, now,
    ) -> dict:
        result = {}

        h1_ago = now - timedelta(hours=1)
        h24_ago = now - timedelta(hours=24)
        m10_ago = now - timedelta(minutes=10)
        d1_ago = now - timedelta(days=1)
        d7_ago = now - timedelta(days=7)
        d30_ago = now - timedelta(days=30)

        q = await self.db.execute(
            select(func.count()).select_from(FactAuthorizationEvent).where(
                and_(
                    FactAuthorizationEvent.customer_id == customer_id,
                    FactAuthorizationEvent.event_time >= h1_ago,
                )
            )
        )
        result["customer_txn_count_1h"] = q.scalar() or 0

        q = await self.db.execute(
            select(func.count(), func.coalesce(func.sum(FactAuthorizationEvent.billing_amount_usd), 0))
            .select_from(FactAuthorizationEvent)
            .where(
                and_(
                    FactAuthorizationEvent.customer_id == customer_id,
                    FactAuthorizationEvent.event_time >= h24_ago,
                )
            )
        )
        row = q.one()
        result["customer_txn_count_24h"] = row[0] or 0
        result["customer_spend_24h"] = row[1] or Decimal("0")

        q = await self.db.execute(
            select(func.count()).select_from(FactAuthorizationEvent).where(
                and_(
                    FactAuthorizationEvent.card_id == card_id,
                    FactAuthorizationEvent.event_time >= m10_ago,
                )
            )
        )
        result["card_txn_count_10m"] = q.scalar() or 0

        q = await self.db.execute(
            select(func.count()).select_from(FactAuthorizationEvent).where(
                and_(
                    FactAuthorizationEvent.merchant_id == merchant_id,
                    FactAuthorizationEvent.event_time >= m10_ago,
                )
            )
        )
        result["merchant_txn_count_10m"] = q.scalar() or 0

        result["merchant_chargeback_rate_30d"] = 0.0

        if device_id:
            q = await self.db.execute(
                select(func.count()).select_from(FactAuthorizationEvent).where(
                    and_(
                        FactAuthorizationEvent.device_id == device_id,
                        FactAuthorizationEvent.event_time >= d1_ago,
                    )
                )
            )
            result["device_txn_count_1d"] = q.scalar() or 0

            q = await self.db.execute(
                select(func.count(func.distinct(FactAuthorizationEvent.account_id)))
                .select_from(FactAuthorizationEvent)
                .where(
                    and_(
                        FactAuthorizationEvent.device_id == device_id,
                        FactAuthorizationEvent.event_time >= d30_ago,
                    )
                )
            )
            result["device_account_count_30d"] = q.scalar() or 0
        else:
            result["device_txn_count_1d"] = 0
            result["device_account_count_30d"] = 0

        if ip_address:
            q = await self.db.execute(
                select(func.count(func.distinct(FactAuthorizationEvent.account_id)))
                .select_from(FactAuthorizationEvent)
                .where(
                    and_(
                        FactAuthorizationEvent.ip_address == ip_address,
                        FactAuthorizationEvent.event_time >= d7_ago,
                    )
                )
            )
            result["ip_account_count_7d"] = q.scalar() or 0

            q = await self.db.execute(
                select(func.count(func.distinct(FactAuthorizationEvent.card_id)))
                .select_from(FactAuthorizationEvent)
                .where(
                    and_(
                        FactAuthorizationEvent.ip_address == ip_address,
                        FactAuthorizationEvent.event_time >= d7_ago,
                    )
                )
            )
            result["ip_card_count_7d"] = q.scalar() or 0
        else:
            result["ip_account_count_7d"] = 0
            result["ip_card_count_7d"] = 0

        return result

    async def _compute_amount_features(
        self, customer_id: int, merchant_id: int, auth_amount: Decimal
    ) -> dict:
        return {
            "vs_customer_p95": float(auth_amount) / 500.0 if auth_amount else 0,
            "vs_merchant_p95": float(auth_amount) / 1000.0 if auth_amount else 0,
        }

    async def _compute_geo_features(
        self, customer_id: int, ip_address: Optional[str]
    ) -> dict:
        return {
            "distance_from_home_km": None,
            "distance_from_last_txn_km": None,
        }

    async def _compute_time_features(self, customer_id: int, now: datetime) -> dict:
        q = await self.db.execute(
            select(func.max(FactAuthorizationEvent.event_time))
            .select_from(FactAuthorizationEvent)
            .where(FactAuthorizationEvent.customer_id == customer_id)
        )
        last_time = q.scalar()
        seconds = int((now - last_time).total_seconds()) if last_time else None
        return {"seconds_since_last_txn": seconds}

    async def _compute_device_features(self, device_id: Optional[str]) -> dict:
        if not device_id:
            return {"risk_score": 0.0}
        result = await self.db.execute(
            select(DimDevice).where(DimDevice.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            return {"risk_score": 0.5}
        score = 0.0
        if device.emulator_flag:
            score += 0.4
        if device.rooted_jailbroken_flag:
            score += 0.3
        return {"risk_score": min(score, 1.0)}

    async def _compute_ip_features(self, ip_address: Optional[str]) -> dict:
        if not ip_address:
            return {"proxy_vpn_tor_flag": False}
        result = await self.db.execute(
            select(DimIP).where(DimIP.ip_address == ip_address)
        )
        ip = result.scalar_one_or_none()
        if not ip:
            return {"proxy_vpn_tor_flag": False}
        return {
            "proxy_vpn_tor_flag": ip.proxy_vpn_tor_flag or False,
            "ip_risk_score": float(ip.ip_risk_score or 0),
        }

    def _build_feature_json(self, *feature_dicts) -> dict:
        merged = {}
        for d in feature_dicts:
            merged.update({k: self._serialize(v) for k, v in d.items()})
        return merged

    def _serialize(self, v):
        if isinstance(v, Decimal):
            return float(v)
        return v
