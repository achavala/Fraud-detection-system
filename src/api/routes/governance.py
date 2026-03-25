"""
/governance endpoints — model cards, contracts, and validation.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.auth import require_role
from src.core.database import get_db
from src.contracts.data_contracts import ContractRegistry
from src.services.governance.model_card import ModelCardService

router = APIRouter(prefix="/governance", tags=["governance"])


@router.get("/model-card/{model_version}")
async def get_model_card(
    model_version: str,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_role("admin", "model_risk", "readonly")),
):
    """Model card for specific version."""
    service = ModelCardService(db)
    try:
        return await service.generate_model_card(model_version)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/model-cards")
async def list_model_cards(db: AsyncSession = Depends(get_db)):
    """List all model cards."""
    service = ModelCardService(db)
    return service.list_model_cards()


@router.get("/compare/{version_a}/{version_b}")
async def compare_models(
    version_a: str,
    version_b: str,
    db: AsyncSession = Depends(get_db),
):
    """Compare two models side-by-side."""
    service = ModelCardService(db)
    try:
        return await service.compare_model_cards(version_a, version_b)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/contracts")
async def list_contracts():
    """List all data contracts."""
    contracts = ContractRegistry.get_all_contracts()
    return {
        "contracts": list(contracts.keys()),
        "schemas": {name: s.model_json_schema() for name, s in contracts.items()},
    }


@router.get("/contracts/validate/auth-event")
async def validate_sample_auth_event():
    """Validate sample auth event against AuthEventContract."""
    sample = {
        "transaction_id": 1001,
        "account_id": 501,
        "card_id": 101,
        "customer_id": 201,
        "merchant_id": 301,
        "device_id": "dev-abc-123",
        "ip_address": "192.168.1.1",
        "auth_type": "card_present",
        "channel": "pos",
        "entry_mode": "chip",
        "auth_amount": Decimal("99.99"),
        "currency_code": "USD",
        "merchant_country_code": "US",
        "billing_amount_usd": Decimal("99.99"),
    }
    valid, errors = ContractRegistry.validate_auth_event(sample)
    sample_serializable = {
        k: float(v) if isinstance(v, Decimal) else v for k, v in sample.items()
    }
    return {
        "valid": valid,
        "sample": sample_serializable,
        "errors": errors,
    }
