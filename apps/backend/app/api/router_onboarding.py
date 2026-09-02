import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.merchant import Merchant
from app.schemas.merchant import MerchantResponse, OnboardMerchantRequest, OnboardMerchantResponse
from app.services.razorpay_client import RazorpayClient

router = APIRouter(tags=["onboarding"])


@router.post("/merchant/onboarding/keys", response_model=OnboardMerchantResponse)
async def set_razorpay_keys(
    payload: OnboardMerchantRequest,
    db: AsyncSession = Depends(get_db),
):
    """Store + validate a merchant's Razorpay test-mode keys."""
    client = RazorpayClient(payload.razorpay_key_id, payload.razorpay_key_secret)
    keys_valid = await client.validate_keys()

    merchant = Merchant(
        name=payload.name,
        razorpay_key_id=payload.razorpay_key_id,
        razorpay_key_secret=payload.razorpay_key_secret,
        status="active" if keys_valid else "pending",
    )
    db.add(merchant)
    await db.flush()
    await db.refresh(merchant)

    return OnboardMerchantResponse(
        merchant=MerchantResponse.model_validate(merchant),
        keys_valid=keys_valid,
    )


@router.get("/merchant/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(merchant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant
