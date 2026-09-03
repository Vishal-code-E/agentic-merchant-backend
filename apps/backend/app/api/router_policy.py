import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.merchant import Merchant
from app.models.policy import Policy
from app.schemas.policy import PolicyResponse, PolicyUpdate

router = APIRouter(tags=["policy"])

_NO_POLICY_DETAIL = (
    "Merchant has no policy configured. Merchants onboarded from v1.2 onward always "
    "have one; this merchant predates that and must be repaired before checkout will work."
)


async def _load_policy(merchant_id: uuid.UUID, db: AsyncSession) -> Policy:
    """
    Resolve a merchant's policy, distinguishing 'no such merchant' (404) from
    'merchant exists but predates the policy-on-onboarding invariant' (409).
    The 409 is a data-repair signal, not a client mistake — see check_policy_node,
    which fails closed in the same situation.
    """
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")

    result = await db.execute(select(Policy).where(Policy.merchant_id == merchant_id).limit(1))
    policy = result.scalars().first()
    if policy is None:
        raise HTTPException(status_code=409, detail=_NO_POLICY_DETAIL)
    return policy


@router.get("/merchant/{merchant_id}/policy", response_model=PolicyResponse)
async def get_policy(merchant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _load_policy(merchant_id, db)


@router.patch("/merchant/{merchant_id}/policy", response_model=PolicyResponse)
async def update_policy(
    merchant_id: uuid.UUID,
    payload: PolicyUpdate,
    db: AsyncSession = Depends(get_db),
):
    policy = await _load_policy(merchant_id, db)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(policy, field, value)

    await db.flush()
    await db.refresh(policy)
    return policy
