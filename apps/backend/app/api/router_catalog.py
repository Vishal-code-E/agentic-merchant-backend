from fastapi import APIRouter

router = APIRouter(tags=["catalog"])


@router.get("/merchant/products")
async def list_merchant_products():
    """Merchant-facing product listing (dashboard). TODO(v1.1)."""
    raise NotImplementedError


@router.get("/agent/catalog")
async def agent_catalog():
    """Agent-readable catalog endpoint (JSON/GraphQL-friendly). TODO(v1.1)."""
    raise NotImplementedError
