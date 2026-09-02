from fastapi import APIRouter

router = APIRouter(tags=["onboarding"])


@router.post("/merchant/onboarding/keys")
async def set_razorpay_keys():
    """Store + validate a merchant's Razorpay test-mode keys. TODO(v1.0)."""
    raise NotImplementedError
