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


def test_manual_worker_commands_do_not_require_email_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAUNCHPAD_SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("LAUNCHPAD_SUPABASE_SERVICE_ROLE_KEY", "service-role-value")
    monkeypatch.delenv("LAUNCHPAD_RESEND_API_KEY", raising=False)
    monkeypatch.delenv("LAUNCHPAD_EMAIL_FROM", raising=False)

    settings = Settings()  # type: ignore[call-arg]

    with pytest.raises(ValueError, match="required for email delivery"):
        settings.require_email_delivery()


def test_email_delivery_settings_are_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAUNCHPAD_SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("LAUNCHPAD_SUPABASE_SERVICE_ROLE_KEY", "service-role-value")
    monkeypatch.setenv("LAUNCHPAD_RESEND_API_KEY", "re_secret_value")
    monkeypatch.setenv(
        "LAUNCHPAD_EMAIL_FROM",
        "Launchpad <alerts@launchpad.test>",
    )
    monkeypatch.setenv("LAUNCHPAD_APP_BASE_URL", "https://launchpad.example.test")

    settings = Settings()  # type: ignore[call-arg]
    api_key, from_address, app_base_url = settings.require_email_delivery()

    assert api_key == "re_secret_value"
    assert from_address == "Launchpad <alerts@launchpad.test>"
    assert app_base_url == "https://launchpad.example.test"
    assert "re_secret_value" not in repr(settings)
