"""Tests for server-only worker configuration."""

import pytest
from pydantic import ValidationError

from launchpad_worker.config import Settings


def test_settings_load_server_only_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAUNCHPAD_SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("LAUNCHPAD_SUPABASE_SERVICE_ROLE_KEY", "service-role-value")

    settings = Settings()  # type: ignore[call-arg]

    assert str(settings.supabase_url) == "https://project.supabase.co/"
    assert settings.supabase_service_role_key.get_secret_value() == "service-role-value"
    assert "service-role-value" not in repr(settings)


def test_settings_reject_placeholder_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAUNCHPAD_SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("LAUNCHPAD_SUPABASE_SERVICE_ROLE_KEY", "your-service-role-key")

    with pytest.raises(ValidationError, match="placeholder"):
        Settings()  # type: ignore[call-arg]
