from functools import lru_cache
from typing import cast

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets are supplied only through environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="development", validation_alias="AGENT_ENVIRONMENT")
    log_level: str = Field(default="INFO", validation_alias="AGENT_LOG_LEVEL")
    tracing_enabled: bool = Field(default=False, validation_alias="AGENT_TRACING_ENABLED")
    max_concurrent_research: int = Field(
        default=1, ge=1, le=1, validation_alias="AGENT_MAX_CONCURRENT_RESEARCH"
    )
    http_timeout_seconds: float = Field(
        default=30.0, gt=0, validation_alias="AGENT_HTTP_TIMEOUT_SECONDS"
    )
    stock_platform_base_url: AnyHttpUrl = Field(
        default=cast(AnyHttpUrl, "http://127.0.0.1:8080"),
        validation_alias="STOCK_PLATFORM_BASE_URL",
    )
    stock_platform_api_token: str | None = Field(
        default=None, validation_alias="STOCK_PLATFORM_API_TOKEN"
    )
    ai_router_base_url: AnyHttpUrl = Field(
        default=cast(AnyHttpUrl, "http://127.0.0.1:8000"),
        validation_alias="AI_ROUTER_BASE_URL",
    )
    ai_router_api_key: str | None = Field(default=None, validation_alias="AI_ROUTER_API_KEY")
    ai_router_logical_model: str = Field(
        default="local-router", validation_alias="AI_ROUTER_LOGICAL_MODEL"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
