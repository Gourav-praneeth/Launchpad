"""Supabase database client construction."""

from supabase import Client, ClientOptions, create_client

from launchpad_worker.config import Settings


def create_database_client(settings: Settings) -> Client:
    """Build a non-persistent service-role client for trusted worker operations."""
    return create_client(
        str(settings.supabase_url).rstrip("/"),
        settings.supabase_service_role_key.get_secret_value(),
        options=ClientOptions(
            auto_refresh_token=False,
            persist_session=False,
        ),
    )
