"""
Configuration settings for the Razorpay Agentic Merchant MCP Server.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # FastAPI backend connection
    backend_base_url: str = Field(default="http://localhost:8000")
    api_v1_prefix: str = Field(default="/api/v1")

    # Optional defaults for single-tenant mode (e.g. Claude Desktop)
    # When set, callers do not need to provide merchant_id or agent_api_key in prompts.
    default_merchant_id: str | None = Field(default=None)
    default_agent_api_key: str | None = Field(default=None)

    # HTTP client configuration
    request_timeout_seconds: float = Field(default=30.0)

    @property
    def api_url(self) -> str:
        base = self.backend_base_url.rstrip("/")
        prefix = self.api_v1_prefix.strip("/")
        return f"{base}/{prefix}" if prefix else base


@lru_cache
def get_mcp_settings() -> MCPSettings:
    return MCPSettings()
