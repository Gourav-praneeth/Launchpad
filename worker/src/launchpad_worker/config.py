"""Validated environment configuration for the discovery worker."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
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
    resend_api_key: SecretStr | None = None
    email_from: str | None = None
    app_base_url: AnyHttpUrl = "http://127.0.0.1:3000"  # type: ignore[assignment]
    notification_max_attempts: int = Field(default=5, ge=1, le=10)

    @field_validator("supabase_service_role_key")
    @classmethod
    def reject_placeholder_key(cls, value: SecretStr) -> SecretStr:
        """Fail fast instead of sending a placeholder credential to Supabase."""
        raw_value = value.get_secret_value()
        if not raw_value or "your-" in raw_value.lower():
            raise ValueError("Supabase service-role key is missing or still a placeholder")
        return value

    @field_validator("resend_api_key")
    @classmethod
    def reject_placeholder_resend_key(cls, value: SecretStr | None) -> SecretStr | None:
        """Validate an optional email credential without requiring it for manual discovery."""
        if value is None:
            return None
        raw_value = value.get_secret_value()
        if not raw_value or "your-" in raw_value.lower():
            raise ValueError("Resend API key is missing or still a placeholder")
        return value

    @field_validator("email_from")
    @classmethod
    def validate_email_from(cls, value: str | None) -> str | None:
        """Keep the provider sender explicit when email delivery is enabled."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or "your-" in normalized.lower() or "@" not in normalized:
            raise ValueError("email sender is invalid or still a placeholder")
        return normalized

    def require_email_delivery(self) -> tuple[str, str, str]:
        """Return provider settings or fail before claiming any notification work."""
        if self.resend_api_key is None or self.email_from is None:
            raise ValueError(
                "LAUNCHPAD_RESEND_API_KEY and LAUNCHPAD_EMAIL_FROM are required for email delivery"
            )
        return (
            self.resend_api_key.get_secret_value(),
            self.email_from,
            str(self.app_base_url).rstrip("/"),
        )


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings instance per worker process."""
    return Settings()  # type: ignore[call-arg]
