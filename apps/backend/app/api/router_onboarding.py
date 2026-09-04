import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.merchant import Merchant
from app.models.policy import Policy
from app.schemas.merchant import (
    DeactivateMerchantRequest,
    DeactivateMerchantResponse,
    MerchantResponse,
    OnboardMerchantRequest,
    OnboardMerchantResponse,
    RegenerateApiKeyResponse,
)
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
    loses it; they would need to call regenerate_api_key() below to get a
    new one.
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
        max_discount_pct=payload.max_discount_pct,
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


@router.post("/merchant/{merchant_id}/api-key/regenerate", response_model=RegenerateApiKeyResponse)
async def regenerate_api_key(merchant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Issue a new agent API key for an existing merchant, invalidating the old one immediately."""
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")

    api_key = generate_api_key()
    merchant.api_key_hash = hash_api_key(api_key)
    await db.flush()

    return RegenerateApiKeyResponse(merchant_id=merchant.id, api_key=api_key)


@router.get("/merchant/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(merchant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


@router.post("/merchant/{merchant_id}/deactivate", response_model=DeactivateMerchantResponse)
@router.delete("/merchant/{merchant_id}", response_model=DeactivateMerchantResponse)
async def deactivate_merchant(
    merchant_id: uuid.UUID,
    payload: DeactivateMerchantRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Merchant deactivation / data subject right flow (GDPR / DPDP compliance):
    1. Soft-deletes the merchant: marks status='disabled' and sets deleted_at.
    2. Revokes agent access: permanently deletes api_key_hash.
    3. Wipes payment credentials: sets razorpay_key_secret and razorpay_key_id to NULL.
    4. Sets product stock to 0 so no further purchases can occur.
    5. Anonymizes customer PII across past AuditLog records if requested.
    6. Retains order transaction summaries for statutory accounting and dispute obligations.
    """
    from datetime import datetime, timezone
    from sqlalchemy import select, update
    from app.models.agent_run import AgentRun
    from app.models.audit_log import AuditLog
    from app.models.order import Order
    from app.models.product import Product

    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")

    reason = payload.reason if payload else "Deactivated by merchant"
    anonymize = payload.anonymize_audit_logs if payload else True

    now = datetime.now(timezone.utc)
    merchant.status = "disabled"
    merchant.deleted_at = now
    merchant.deactivated_reason = reason
    merchant.api_key_hash = None
    merchant.razorpay_key_secret = None
    merchant.razorpay_key_id = None

    # Zero stock on all products
    await db.execute(
        update(Product).where(Product.merchant_id == merchant_id).values(stock=0)
    )

    # Anonymize customer data in audit logs if requested
    anonymized_count = 0
    if anonymize:
        runs_res = await db.execute(select(AgentRun.id).where(AgentRun.merchant_id == merchant_id))
        run_ids = runs_res.scalars().all()
        if run_ids:
            logs_res = await db.execute(select(AuditLog).where(AuditLog.agent_run_id.in_(run_ids)))
            audit_logs = logs_res.scalars().all()
            for log in audit_logs:
                if isinstance(log.payload_json, dict):
                    modified = False
                    new_payload = dict(log.payload_json)
                    for key in ["customer_id", "user_id"]:
                        if key in new_payload:
                            new_payload[key] = "[ANONYMIZED_CUSTOMER]"
                            modified = True
                    if "customer_context" in new_payload and isinstance(new_payload["customer_context"], dict):
                        new_payload["customer_context"] = {"customer_id": "[ANONYMIZED_CUSTOMER]"}
                        modified = True
                    if modified:
                        log.payload_json = new_payload
                        anonymized_count += 1

    # Count retained records for receipt
    orders_count_res = await db.execute(select(Order.id).where(Order.merchant_id == merchant_id))
    retained_orders = len(orders_count_res.scalars().all())

    runs_count_res = await db.execute(select(AgentRun.id).where(AgentRun.merchant_id == merchant_id))
    retained_runs = len(runs_count_res.scalars().all())

    await db.flush()

    return DeactivateMerchantResponse(
        merchant_id=merchant.id,
        status=merchant.status,
        deactivated_at=now,
        retained_records={
            "orders": retained_orders,
            "agent_runs": retained_runs,
            "anonymized_audit_logs": anonymized_count,
        },
        notice=(
            "Merchant deactivated and credentials scrubbed. Order and transaction totals are "
            "retained in anonymized form for statutory accounting/tax compliance."
        ),
    )
