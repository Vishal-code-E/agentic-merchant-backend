import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api import (
    router_campaigns,
    router_catalog,
    router_checkout,
    router_observability,
    router_onboarding,
    router_policy,
)
from app.config.settings import get_settings
from app.db.session import engine
from app.observability.langfuse_client import get_langfuse_client

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    # Soft check only — unlike the DB, Langfuse being unreachable/misconfigured
    # shouldn't block the app from starting, but should be loud in the logs.
    langfuse = get_langfuse_client()
    if not await asyncio.to_thread(langfuse.auth_check):
        logger.warning(
            "Langfuse auth_check() failed — traces will not reach Langfuse. "
            "Check LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY/LANGFUSE_BASE_URL."
        )

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
app.include_router(router_policy.router, prefix=settings.api_v1_prefix)
app.include_router(router_observability.router, prefix=settings.api_v1_prefix)
app.include_router(router_campaigns.router, prefix=settings.api_v1_prefix)
