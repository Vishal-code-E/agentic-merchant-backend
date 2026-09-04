"""
Centralized app configuration.

All secrets (Razorpay keys, DB URL, model provider keys) are loaded from
environment variables / .env — never hardcoded, never logged.
See /.env.example at repo root for the full variable list.
"""
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "Razorpay Agentic Merchant Backend"
    app_env: str = Field(default="dev")  # dev | test | prod
    api_v1_prefix: str = "/api/v1"

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/agentic_merchant"
    )

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0")

    # --- Razorpay (test mode only for v1) ---
    razorpay_key_id: str = Field(default="")
    razorpay_key_secret: str = Field(default="")
    razorpay_webhook_secret: str = Field(default="")

    # --- Observability ---
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    # Matches the Python SDK v4 env var (LANGFUSE_BASE_URL) and constructor
    # kwarg (base_url) — the older LANGFUSE_HOST/host naming is SDK v2-era.
    langfuse_base_url: str = Field(default="https://cloud.langfuse.com")
    data_retention_days: int = Field(default=90, description="Retention window for audit logs and agent runs in days")

    # --- Model provider (universal abstraction; config-driven) ---
    model_provider: str = Field(default="anthropic")  # anthropic | openai | gemini
    anthropic_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")

    # --- CORS ---
    # Comma-separated list of origins allowed to call the API from a browser
    # (see app/main.py's CORSMiddleware). Defaults to just the local frontend
    # dev server so this isn't hardcoded for production later.
    cors_allowed_origins: str = Field(default="http://localhost:3000")

    # --- Security ---
    secret_key: str = Field(default="change-me-in-prod")
    # Fernet key used to encrypt merchant Razorpay secrets at rest. No default —
    # must fail at startup in prod rather than silently storing plaintext.
    encryption_key: str = Field(default="")

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        """cors_allowed_origins, split on commas and trimmed, for CORSMiddleware(allow_origins=...)."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _require_encryption_key_in_prod(self) -> "Settings":
        if self.app_env == "prod" and not self.encryption_key:
            raise ValueError(
                "ENCRYPTION_KEY must be set in prod (used to encrypt merchant "
                "Razorpay secrets at rest). Generate one with: "
                "python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — import this, don't instantiate Settings() directly."""
    return Settings()
