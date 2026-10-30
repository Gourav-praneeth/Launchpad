"""Tests for Supabase client construction."""

from unittest.mock import Mock, patch

from pydantic import SecretStr

from launchpad_worker.config import Settings
from launchpad_worker.database import create_database_client


def test_database_client_uses_service_role_without_persisting_session() -> None:
    settings = Settings(
        supabase_url="https://project.supabase.co",  # type: ignore[arg-type]
        supabase_service_role_key=SecretStr("service-role-value"),
    )
    expected_client = Mock()

    with patch("launchpad_worker.database.create_client", return_value=expected_client) as factory:
        client = create_database_client(settings)

    assert client is expected_client
    factory.assert_called_once()
    assert factory.call_args.args[:2] == (
        "https://project.supabase.co",
        "service-role-value",
    )
    options = factory.call_args.kwargs["options"]
    assert options.auto_refresh_token is False
    assert options.persist_session is False
