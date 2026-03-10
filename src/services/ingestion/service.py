"""
Service 1: Ingestion Service
Consumes card auth events, device telemetry, IP intel, merchant metadata,
customer/account updates, chargebacks/disputes, and rules outcomes.
Writes to Postgres raw/curated tables and event/audit stream.
"""
from __future__ import annotations

from datetime import datetime, timezone, date as date_type
from decimal import Decimal
from typing import Optional, Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.dimensions import (
    DimCustomer, DimAccount, DimCard, DimMerchant, DimDevice, DimIP,
)
from src.models.transactions import (
    FactAuthorizationEvent, FactClearingEvent, FactTransactionLifecycleEvent,
)
from src.models.labels import FactFraudLabel, FactChargebackCase
from src.models.audit import AuditEvent

logger = get_logger(__name__)


class IngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest_authorization(
        self,
        transaction_id: int,
        account_id: int,
        card_id: int,
        customer_id: int,
        merchant_id: int,
        auth_type: str,
        channel: str,
        auth_amount: Decimal,
        currency_code: str,
        merchant_country_code: str,
        device_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        entry_mode: Optional[str] = None,
        billing_amount_usd: Optional[Decimal] = None,
        request_payload: Optional[dict] = None,
    ) -> FactAuthorizationEvent:
        now = datetime.now(timezone.utc)
        event = FactAuthorizationEvent(
            transaction_id=transaction_id,
            event_time=now,
            account_id=account_id,
            card_id=card_id,
            customer_id=customer_id,
            merchant_id=merchant_id,
            device_id=device_id,
            ip_address=ip_address,
            auth_type=auth_type,
            channel=channel,
            entry_mode=entry_mode,
            auth_amount=auth_amount,
            currency_code=currency_code,
            merchant_country_code=merchant_country_code,
            billing_amount_usd=billing_amount_usd or auth_amount,
            auth_status="pending",
            request_payload_json=request_payload,
        )
        self.db.add(event)
        await self.db.flush()

        await self._emit_lifecycle_event(
            transaction_id=transaction_id,
            auth_event_id=event.auth_event_id,
            event_type="auth_received",
            actor_type="system",
            actor_id="ingestion_service",
        )

        await self._emit_audit(
            entity_type="authorization",
            entity_id=str(event.auth_event_id),
            event_type="auth_ingested",
            payload={"transaction_id": transaction_id, "amount": str(auth_amount)},
        )

        logger.info(
            "authorization_ingested",
            auth_event_id=event.auth_event_id,
            transaction_id=transaction_id,
        )
        return event

    async def ingest_clearing(
        self,
        transaction_id: int,
        auth_event_id: int,
        clearing_amount: Decimal,
        currency_code: str,
        settlement_status: str,
    ) -> FactClearingEvent:
        event = FactClearingEvent(
            transaction_id=transaction_id,
            auth_event_id=auth_event_id,
            clearing_time=datetime.now(timezone.utc),
            clearing_amount=clearing_amount,
            currency_code=currency_code,
            settlement_status=settlement_status,
        )
        self.db.add(event)
        await self.db.flush()

        await self._emit_lifecycle_event(
            transaction_id=transaction_id,
            auth_event_id=auth_event_id,
            event_type="clearing_received",
            actor_type="system",
            actor_id="ingestion_service",
            payload={"settlement_status": settlement_status},
        )
        return event

    async def ingest_chargeback(
        self,
        transaction_id: int,
        auth_event_id: int,
        reason_code: str,
        amount: Decimal,
        representment_flag: bool = False,
    ) -> FactChargebackCase:
        chargeback = FactChargebackCase(
            transaction_id=transaction_id,
            auth_event_id=auth_event_id,
            chargeback_reason_code=reason_code,
            chargeback_amount=amount,
            chargeback_received_at=datetime.now(timezone.utc),
            representment_flag=representment_flag,
        )
        self.db.add(chargeback)
        await self.db.flush()

        await self._emit_lifecycle_event(
            transaction_id=transaction_id,
            auth_event_id=auth_event_id,
            event_type="chargeback_received",
            actor_type="system",
            actor_id="ingestion_service",
            payload={"reason_code": reason_code, "amount": str(amount)},
        )

        await self._emit_audit(
            entity_type="chargeback",
            entity_id=str(chargeback.chargeback_id),
            event_type="chargeback_ingested",
            payload={"auth_event_id": auth_event_id, "reason_code": reason_code},
        )

        logger.info("chargeback_ingested", chargeback_id=chargeback.chargeback_id)
        return chargeback

    async def ingest_fraud_label(
        self,
        auth_event_id: int,
        transaction_id: int,
        label_type: str,
        is_fraud: bool,
        label_source: str,
        fraud_category: Optional[str] = None,
        fraud_subcategory: Optional[str] = None,
        source_confidence: float = 1.0,
        investigator_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> FactFraudLabel:
        now = datetime.now(timezone.utc)
        label = FactFraudLabel(
            auth_event_id=auth_event_id,
            transaction_id=transaction_id,
            label_type=label_type,
            is_fraud=is_fraud,
            fraud_category=fraud_category,
            fraud_subcategory=fraud_subcategory,
            label_source=label_source,
            source_confidence=source_confidence,
            label_received_at=now,
            effective_label_date=now.date(),
            investigator_id=investigator_id,
            notes=notes,
        )
        self.db.add(label)
        await self.db.flush()

        await self._emit_lifecycle_event(
            transaction_id=transaction_id,
            auth_event_id=auth_event_id,
            event_type="label_confirmed",
            actor_type="investigator" if investigator_id else "system",
            actor_id=investigator_id or "label_service",
            payload={"is_fraud": is_fraud, "source": label_source},
        )
        return label

    async def upsert_customer(
        self,
        external_ref: str,
        kyc_status: str = "pending",
        risk_segment: str = "low",
        home_country_code: str = "US",
        **kwargs,
    ) -> DimCustomer:
        result = await self.db.execute(
            select(DimCustomer).where(DimCustomer.external_customer_ref == external_ref)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.kyc_status = kyc_status
            existing.risk_segment = risk_segment
            existing.updated_at = datetime.now(timezone.utc)
            return existing

        customer = DimCustomer(
            external_customer_ref=external_ref,
            customer_since_dt=kwargs.get("customer_since_dt", datetime.now(timezone.utc).date()),
            kyc_status=kyc_status,
            risk_segment=risk_segment,
            home_country_code=home_country_code,
            home_region=kwargs.get("home_region"),
            birth_year=kwargs.get("birth_year"),
        )
        self.db.add(customer)
        await self.db.flush()
        return customer

    async def upsert_device(
        self,
        device_id: str,
        device_fingerprint: str,
        os_family: Optional[str] = None,
        app_version: Optional[str] = None,
        browser_family: Optional[str] = None,
        emulator_flag: bool = False,
        rooted_jailbroken_flag: bool = False,
    ) -> DimDevice:
        result = await self.db.execute(
            select(DimDevice).where(DimDevice.device_id == device_id)
        )
        existing = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if existing:
            existing.last_seen_at = now
            existing.device_fingerprint = device_fingerprint
            return existing

        device = DimDevice(
            device_id=device_id,
            device_fingerprint=device_fingerprint,
            os_family=os_family,
            app_version=app_version,
            browser_family=browser_family,
            emulator_flag=emulator_flag,
            rooted_jailbroken_flag=rooted_jailbroken_flag,
            first_seen_at=now,
            last_seen_at=now,
        )
        self.db.add(device)
        await self.db.flush()
        return device

    async def _emit_lifecycle_event(
        self,
        transaction_id: int,
        auth_event_id: int,
        event_type: str,
        actor_type: str,
        actor_id: str,
        payload: Optional[dict] = None,
    ):
        event = FactTransactionLifecycleEvent(
            transaction_id=transaction_id,
            auth_event_id=auth_event_id,
            event_type=event_type,
            event_time=datetime.now(timezone.utc),
            actor_type=actor_type,
            actor_id=actor_id,
            payload_json=payload,
        )
        self.db.add(event)

    async def _emit_audit(
        self,
        entity_type: str,
        entity_id: str,
        event_type: str,
        payload: Optional[dict] = None,
    ):
        audit = AuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            payload_json=payload,
        )
        self.db.add(audit)
