import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.merchant import Merchant
from app.models.policy import Policy
from app.schemas.merchant import MerchantResponse, OnboardMerchantRequest, OnboardMerchantResponse
from app.schemas.policy import PolicyResponse
from app.services.agent_auth import generate_api_key, hash_api_key
from app.services.encryption import encrypt_secret
from app.services.razorpay_client import RazorpayClient

router = APIRouter(tags=["onboarding"])


@router.post("/merchant/onboarding/keys", response_model=OnboardMerchantResponse)
async def set_razorpay_keys(
    payload: OnboardMerchantRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Store + validate a merchant's Razorpay test-mode keys, create the
    merchant's Policy row, and issue an agent API key — all in the same
    transaction.

    A Merchant without a Policy is not a valid state: check_policy_node fails
    closed on a missing policy, so a half-written merchant would be permanently
    un-checkout-able. All rows are added to the same session and flushed once;
    get_db() commits only after this handler returns, and rolls back on any
    exception, so a failure on any INSERT persists none of them.

    The plaintext agent API key exists only in this function's local variable
    and in the response below — only its sha256 hash is ever persisted (see
    app/services/agent_auth.py) — so it cannot be recovered if the caller
    loses it; they would need to re-onboard (or a future key-rotation
    endpoint) to get a new one.
    """
    client = RazorpayClient(payload.razorpay_key_id, payload.razorpay_key_secret)
    keys_valid = await client.validate_keys()

    api_key = generate_api_key()

    merchant = Merchant(
        name=payload.name,
        razorpay_key_id=payload.razorpay_key_id,
        razorpay_key_secret=encrypt_secret(payload.razorpay_key_secret),
        status="active" if keys_valid else "pending",
        api_key_hash=hash_api_key(api_key),
    )
    db.add(merchant)

    policy = Policy(
        merchant=merchant,
        max_amount=payload.max_amount,
        allowed_categories=payload.allowed_categories,
        per_user_limit=payload.per_user_limit,
        rules_json={},
    )
    db.add(policy)

    # Single flush: SQLAlchemy orders the INSERTs by FK dependency, so the
    # merchant PK is populated and assigned to policy.merchant_id without an
    # intermediate flush/commit.
    await db.flush()
    await db.refresh(merchant)
    await db.refresh(policy)

    return OnboardMerchantResponse(
        merchant=MerchantResponse.model_validate(merchant),
        policy=PolicyResponse.model_validate(policy),
        keys_valid=keys_valid,
        api_key=api_key,
    )


@router.get("/merchant/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(merchant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant
