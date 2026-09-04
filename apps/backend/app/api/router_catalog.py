import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.merchant import Merchant
from app.models.product import Product
from app.schemas.product import AgentCatalogItem, ProductCreate, ProductResponse, ProductUpdate
from app.services.agent_auth import verify_agent_api_key

router = APIRouter(tags=["catalog"])


@router.post("/merchant/products", response_model=ProductResponse, status_code=201)
async def create_product(payload: ProductCreate, db: AsyncSession = Depends(get_db)):
    """Merchant-facing product creation (dashboard)."""
    merchant = await db.get(Merchant, payload.merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")

    product = Product(**payload.model_dump())
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


@router.get("/merchant/products", response_model=list[ProductResponse])
async def list_merchant_products(merchant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Merchant-facing product listing (dashboard), scoped to one merchant."""
    result = await db.execute(select(Product).where(Product.merchant_id == merchant_id))
    return result.scalars().all()


@router.patch("/merchant/products/{product_id}", response_model=ProductResponse)
async def update_product(product_id: uuid.UUID, payload: ProductUpdate, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    await db.flush()
    await db.refresh(product)
    return product


@router.delete("/merchant/products/{product_id}", status_code=204)
async def delete_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    await db.delete(product)


@router.get("/agent/catalog", response_model=list[AgentCatalogItem])
async def agent_catalog(
    merchant_id: uuid.UUID,
    category: str | None = None,
    max_price: float | None = None,
    x_agent_api_key: str | None = Header(default=None, alias="X-Agent-Api-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Agent-readable catalog endpoint: flat JSON array, no nested objects."""
    await verify_agent_api_key(merchant_id, x_agent_api_key, db)

    query = select(Product).where(Product.merchant_id == merchant_id)
    if category is not None:
        query = query.where(Product.category == category)
    if max_price is not None:
        query = query.where(Product.price <= max_price)

    result = await db.execute(query)
    return result.scalars().all()
