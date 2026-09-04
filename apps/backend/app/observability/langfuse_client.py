"""
Langfuse client + CallbackHandler setup (Python SDK v4, OpenTelemetry-based).

get_langfuse_client() explicitly constructs the process-wide Langfuse
singleton from our own Settings (rather than letting the SDK read raw
LANGFUSE_* env vars itself), so config stays centralized the same way
RazorpayClient/encryption/DB already go through app.config.settings.
Subsequent get_client() calls anywhere in the app return this same instance.

get_langfuse_handler() returns a CallbackHandler for LangGraph/LangChain
tracing. As of SDK v4, CallbackHandler() takes no constructor arguments —
all config lives on the Langfuse client — so this only has to guarantee the
client above has been initialized first.
"""
from functools import lru_cache

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app.config.settings import get_settings


@lru_cache
def get_langfuse_client() -> Langfuse:
    """Cached Langfuse client singleton, built from settings."""
    settings = get_settings()
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
        environment=settings.app_env,
    )


@lru_cache
def get_langfuse_handler() -> CallbackHandler:
    """Cached CallbackHandler for passing into graph.ainvoke(config={"callbacks": [...]})."""
    get_langfuse_client()  # ensure the singleton above is the one CallbackHandler() binds to
    return CallbackHandler()
