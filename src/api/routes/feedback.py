"""
/feedback endpoints — label ingestion, chargebacks, and truth management.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import require_role
from src.core.database import get_db
from src.services.ingestion.service import IngestionService
from src.schemas.labels import FraudLabelCreate, ChargebackCreate, LabelSnapshotRequest

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/label")
async def submit_fraud_label(
    request: FraudLabelCreate,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_role("admin", "investigator")),
):
    """Submit a fraud label — delayed truth from any source."""
    service = IngestionService(db)
    label = await service.ingest_fraud_label(
        auth_event_id=request.auth_event_id,
        transaction_id=request.transaction_id,
        label_type=request.label_type,
        is_fraud=request.is_fraud,
        label_source=request.label_source,
        fraud_category=request.fraud_category,
        fraud_subcategory=request.fraud_subcategory,
        source_confidence=request.source_confidence,
        investigator_id=request.investigator_id,
        notes=request.notes,
    )
    return {
        "label_id": label.label_id,
        "auth_event_id": label.auth_event_id,
        "is_fraud": label.is_fraud,
        "label_source": label.label_source,
    }


@router.post("/chargeback")
async def submit_chargeback(
    request: ChargebackCreate,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_role("admin", "investigator")),
):
    """Ingest a chargeback event."""
    service = IngestionService(db)
    cb = await service.ingest_chargeback(
        transaction_id=request.transaction_id,
        auth_event_id=request.auth_event_id,
        reason_code=request.chargeback_reason_code,
        amount=request.chargeback_amount,
        representment_flag=request.representment_flag,
    )
    return {
        "chargeback_id": cb.chargeback_id,
        "auth_event_id": cb.auth_event_id,
        "reason_code": cb.chargeback_reason_code,
    }
