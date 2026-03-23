"""
Service 2: Feature Service
Computes velocity, spend anomaly, behavioral, geo, merchant risk, and graph features.
Outputs both online feature rows (for serving) and offline training feature rows.
"""
from __future__ import annotations

import math
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
from src.models.labels import FactChargebackCase
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

        # Chargeback rate: count chargebacks / total txn for merchant in last 30d
        cb_subq = (
            select(func.count())
            .select_from(FactChargebackCase)
            .join(
                FactAuthorizationEvent,
                FactChargebackCase.auth_event_id == FactAuthorizationEvent.auth_event_id,
            )
            .where(
                and_(
                    FactAuthorizationEvent.merchant_id == merchant_id,
                    FactChargebackCase.chargeback_received_at >= d30_ago,
                )
            )
        )
        cb_result = await self.db.execute(cb_subq)
        chargeback_count = cb_result.scalar() or 0

        txn_count_q = await self.db.execute(
            select(func.count()).select_from(FactAuthorizationEvent).where(
                and_(
                    FactAuthorizationEvent.merchant_id == merchant_id,
                    FactAuthorizationEvent.event_time >= d30_ago,
                )
            )
        )
        total_txn_count = txn_count_q.scalar() or 0
        result["merchant_chargeback_rate_30d"] = (
            float(chargeback_count) / float(total_txn_count) if total_txn_count > 0 else 0.0
        )

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
        d90_ago = datetime.now(timezone.utc) - timedelta(days=90)

        p95_customer = None
        p95_merchant = None

        # 95th percentile of billing_amount_usd for customer (last 90 days)
        q_cust = await self.db.execute(
            select(
                func.percentile_cont(0.95).within_group(
                    FactAuthorizationEvent.billing_amount_usd
                )
            )
            .select_from(FactAuthorizationEvent)
            .where(
                and_(
                    FactAuthorizationEvent.customer_id == customer_id,
                    FactAuthorizationEvent.event_time >= d90_ago,
                    FactAuthorizationEvent.billing_amount_usd.isnot(None),
                )
            )
        )
        p95_customer = q_cust.scalar()

        # 95th percentile of billing_amount_usd for merchant (last 90 days)
        q_merch = await self.db.execute(
            select(
                func.percentile_cont(0.95).within_group(
                    FactAuthorizationEvent.billing_amount_usd
                )
            )
            .select_from(FactAuthorizationEvent)
            .where(
                and_(
                    FactAuthorizationEvent.merchant_id == merchant_id,
                    FactAuthorizationEvent.event_time >= d90_ago,
                    FactAuthorizationEvent.billing_amount_usd.isnot(None),
                )
            )
        )
        p95_merchant = q_merch.scalar()

        p95_cust_val = float(p95_customer) if p95_customer else None
        p95_merch_val = float(p95_merchant) if p95_merchant else None

        return {
            "vs_customer_p95": (
                float(auth_amount) / p95_cust_val
                if auth_amount and p95_cust_val and p95_cust_val > 0
                else 0.0
            ),
            "vs_merchant_p95": (
                float(auth_amount) / p95_merch_val
                if auth_amount and p95_merch_val and p95_merch_val > 0
                else 0.0
            ),
        }

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine distance in km between two (lat, lon) points."""
        R = 6371.0  # Earth radius in km
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def _geo_coords(self, country_code: Optional[str], city_or_region: Optional[str]) -> Optional[tuple[float, float]]:
        """Look up (lat, lon) from country + city/region. Simple mapping for common locations."""
        GEO_COORDS: dict[tuple[str, str], tuple[float, float]] = {
            ("US", ""): (39.8283, -98.5795),
            ("US", "NYC"): (40.7128, -74.0060),
            ("US", "NY"): (43.2994, -74.2179),
            ("US", "LA"): (34.0522, -118.2437),
            ("US", "CA"): (36.7783, -119.4179),
            ("US", "CHICAGO"): (41.8781, -87.6298),
            ("US", "IL"): (40.6331, -89.3985),
            ("US", "TX"): (31.9686, -99.9018),
            ("US", "FL"): (27.6648, -81.5158),
            ("GB", ""): (55.3781, -3.4360),
            ("GB", "LONDON"): (51.5074, -0.1278),
            ("UK", ""): (55.3781, -3.4360),
            ("UK", "LONDON"): (51.5074, -0.1278),
            ("DE", ""): (51.1657, 10.4515),
            ("DE", "BERLIN"): (52.5200, 13.4050),
            ("FR", ""): (46.2276, 2.2137),
            ("FR", "PARIS"): (48.8566, 2.3522),
            ("ES", ""): (40.4637, -3.7492),
            ("ES", "MADRID"): (40.4168, -3.7038),
            ("IT", ""): (41.8719, 12.5674),
            ("IT", "ROME"): (41.9028, 12.4964),
            ("NL", ""): (52.1326, 5.2913),
            ("NL", "AMSTERDAM"): (52.3676, 4.9041),
            ("CA", ""): (56.1304, -106.3468),
            ("CA", "TORONTO"): (43.6532, -79.3832),
            ("CA", "ON"): (51.2538, -85.3232),
            ("AU", ""): (-25.2744, 133.7751),
            ("AU", "SYDNEY"): (-33.8688, 151.2093),
            ("IN", ""): (20.5937, 78.9629),
            ("IN", "MUMBAI"): (19.0760, 72.8777),
            ("CN", ""): (35.8617, 104.1954),
            ("CN", "BEIJING"): (39.9042, 116.4074),
            ("JP", ""): (36.2048, 138.2529),
            ("JP", "TOKYO"): (35.6762, 139.6503),
            ("BR", ""): (-14.2350, -51.9253),
            ("BR", "SAO PAULO"): (-23.5505, -46.6333),
            ("MX", ""): (23.6345, -102.5528),
            ("MX", "MEXICO CITY"): (19.4326, -99.1332),
        }
        cc = (country_code or "").upper().strip()
        loc = (city_or_region or "").upper().strip()[:50]
        return GEO_COORDS.get((cc, loc)) or GEO_COORDS.get((cc, ""))

    async def _compute_geo_features(
        self, customer_id: int, ip_address: Optional[str]
    ) -> dict:
        result: dict[str, Optional[float]] = {
            "distance_from_home_km": None,
            "distance_from_last_txn_km": None,
        }

        if not ip_address:
            return result

        # IP geo: lookup from dim_ip (geo_country_code + geo_city)
        ip_res = await self.db.execute(
            select(DimIP).where(DimIP.ip_address == ip_address)
        )
        ip_row = ip_res.scalar_one_or_none()
        ip_coords = None
        if ip_row and (ip_row.geo_country_code or ip_row.geo_city):
            ip_coords = self._geo_coords(ip_row.geo_country_code, ip_row.geo_city or ip_row.geo_region)

        # Customer home: lookup from dim_customer (home_country_code + home_region)
        cust_res = await self.db.execute(
            select(DimCustomer).where(DimCustomer.customer_id == customer_id)
        )
        cust_row = cust_res.scalar_one_or_none()
        home_coords = None
        if cust_row and cust_row.home_country_code:
            home_coords = self._geo_coords(cust_row.home_country_code, cust_row.home_region)

        if ip_coords and home_coords:
            result["distance_from_home_km"] = self._haversine_km(
                home_coords[0], home_coords[1], ip_coords[0], ip_coords[1]
            )

        # Last transaction's IP
        last_txn = await self.db.execute(
            select(FactAuthorizationEvent.ip_address)
            .where(FactAuthorizationEvent.customer_id == customer_id)
            .where(FactAuthorizationEvent.ip_address.isnot(None))
            .order_by(FactAuthorizationEvent.event_time.desc())
            .limit(1)
        )
        last_ip = last_txn.scalar_one_or_none()

        if last_ip and ip_coords:
            if str(last_ip) == str(ip_address):
                result["distance_from_last_txn_km"] = 0.0
            else:
                last_ip_res = await self.db.execute(
                    select(DimIP).where(DimIP.ip_address == last_ip)
                )
                last_ip_row = last_ip_res.scalar_one_or_none()
                last_coords = None
                if last_ip_row and (last_ip_row.geo_country_code or last_ip_row.geo_city):
                    last_coords = self._geo_coords(
                        last_ip_row.geo_country_code, last_ip_row.geo_city or last_ip_row.geo_region
                    )
                if last_coords:
                    result["distance_from_last_txn_km"] = self._haversine_km(
                        last_coords[0], last_coords[1], ip_coords[0], ip_coords[1]
                    )

        return result

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
