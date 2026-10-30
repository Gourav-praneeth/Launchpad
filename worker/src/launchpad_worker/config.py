"""Validated environment configuration for the discovery worker."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-only worker settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_prefix="LAUNCHPAD_",
        extra="ignore",
        case_sensitive=False,
    )

    supabase_url: AnyHttpUrl
    supabase_service_role_key: SecretStr
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["console", "json"] = "console"

    @field_validator("supabase_service_role_key")
    @classmethod
    def reject_placeholder_key(cls, value: SecretStr) -> SecretStr:
        """Fail fast instead of sending a placeholder credential to Supabase."""
        raw_value = value.get_secret_value()
        if not raw_value or "your-" in raw_value.lower():
            raise ValueError("Supabase service-role key is missing or still a placeholder")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per worker process."""
    return Settings()  # type: ignore[call-arg]
