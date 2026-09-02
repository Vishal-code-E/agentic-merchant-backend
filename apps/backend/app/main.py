from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api import (
    router_catalog,
    router_checkout,
    router_observability,
    router_onboarding,
)
from app.config.settings import get_settings
from app.db.session import engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Agentic backend that makes a Razorpay merchant AI-sellable (test-mode).",
    lifespan=lifespan,
)


@app.get("/ping", tags=["health"])
async def ping():
    """Simple liveness check — the one endpoint in this skeleton that actually works."""
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/health/db", tags=["health"])
async def health_db():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}


app.include_router(router_onboarding.router, prefix=settings.api_v1_prefix)
app.include_router(router_catalog.router, prefix=settings.api_v1_prefix)
app.include_router(router_checkout.router, prefix=settings.api_v1_prefix)
app.include_router(router_observability.router, prefix=settings.api_v1_prefix)
