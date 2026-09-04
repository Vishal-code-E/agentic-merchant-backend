import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

# Browser-only protection — curl/httpx never hit this, only requests sent
# from a page running in a browser (e.g. the dashboard on localhost:3000).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# Registration order matters: FastAPI/Starlette matches routes in the order
# they were added, with no static-vs-dynamic specificity scoring. router_catalog's
# static "/merchant/products" must be registered before router_onboarding's
# dynamic "/merchant/{merchant_id}" — both are two path segments, so a
# GET /merchant/products request would otherwise match the dynamic route first,
# with "products" failing UUID validation as merchant_id (422).
app.include_router(router_catalog.router, prefix=settings.api_v1_prefix)
app.include_router(router_onboarding.router, prefix=settings.api_v1_prefix)
app.include_router(router_checkout.router, prefix=settings.api_v1_prefix)
app.include_router(router_policy.router, prefix=settings.api_v1_prefix)
app.include_router(router_observability.router, prefix=settings.api_v1_prefix)
app.include_router(router_campaigns.router, prefix=settings.api_v1_prefix)
