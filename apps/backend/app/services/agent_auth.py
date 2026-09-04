"""
Agent API key generation + verification for the /agent/* endpoints.

An agent API key is only ever compared, never decrypted, so it's hashed
one-way with sha256 (constant-time compared via hmac.compare_digest) instead
of Fernet-encrypted like merchant.razorpay_key_secret (see
app/services/encryption.py) — this is a bearer-token comparison, not a login
password needing bcrypt/argon2's deliberate slowness.
"""
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant import Merchant

_INVALID_KEY_DETAIL = (
    "Missing or invalid X-Agent-Api-Key header. Obtain a key from "
    "POST /merchant/onboarding/keys — it is returned once, at onboarding time."
)


def generate_api_key() -> str:
    """A random, URL-safe agent API key. Returned to the caller exactly once, at onboarding."""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


async def verify_agent_api_key(merchant_id: uuid.UUID, api_key: str | None, db: AsyncSession) -> None:
    """
    Raise 401 unless api_key hashes to this merchant's stored api_key_hash.

    Deliberately a plain async helper, not a FastAPI Depends callable:
    merchant_id comes from a query param on GET /agent/catalog and from a
    request-body field on POST /agent/checkout, so each router resolves
    merchant_id first and calls this explicitly — the same shape as
    router_policy.py's _load_policy() helper.

    Fails closed for merchants with no api_key_hash on record (onboarded
    before this feature existed) — there is no key that could ever satisfy
    an unset hash, by design. Same posture as check_policy_node failing
    closed on a missing Policy row.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail=_INVALID_KEY_DETAIL)

    merchant = await db.get(Merchant, merchant_id)
    if merchant is None or not merchant.api_key_hash:
        raise HTTPException(status_code=401, detail=_INVALID_KEY_DETAIL)

    if not hmac.compare_digest(hash_api_key(api_key), merchant.api_key_hash):
        raise HTTPException(status_code=401, detail=_INVALID_KEY_DETAIL)

    if merchant.status == "disabled" or merchant.deleted_at is not None:
        raise HTTPException(
            status_code=403,
            detail="Merchant account has been deactivated. Agent access is disabled.",
        )

    # Fire-and-forget: mutate the already-loaded row, no extra flush/commit here —
    # it rides along in whichever commit the caller's request does anyway.
    merchant.last_used_at = datetime.now(timezone.utc)
