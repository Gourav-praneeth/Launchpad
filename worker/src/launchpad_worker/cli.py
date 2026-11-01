"""Command-line interface for operational worker runs."""

import argparse
from collections.abc import Sequence
from typing import cast
from uuid import UUID

import structlog

from launchpad_worker.automation import (
    AutomationPersistenceError,
    AutomationRepository,
    AutomationRunner,
    ConfiguredMatchingOperation,
    ConfiguredSourceOperation,
)
from launchpad_worker.config import Settings, get_settings
from launchpad_worker.database import create_database_client
from launchpad_worker.discovery import DiscoveryRunner
from launchpad_worker.logging import configure_logging
from launchpad_worker.matching_persistence import (
    MatchingPersistenceError,
    MatchingRepository,
    MatchingRunner,
)
from launchpad_worker.notifications import (
    NotificationDispatcher,
    NotificationPersistenceError,
    NotificationRepository,
    ResendEmailProvider,
)
from launchpad_worker.persistence import (
    DatabaseClient,
    DiscoveryPersistenceError,
    DiscoveryRepository,
)
from launchpad_worker.source_registry import (
    SourceRegistry,
    SourceRegistryError,
    TableClient,
    build_job_source,
)
from launchpad_worker.sources import SourceFetchError


def build_parser() -> argparse.ArgumentParser:
    """Build the worker CLI without reading environment configuration."""
    parser = argparse.ArgumentParser(
        prog="launchpad-worker",
        description="Run Launchpad discovery and matching operations.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    discover = subcommands.add_parser(
        "discover",
        help="Fetch and atomically persist one configured source.",
    )
    discover.add_argument(
        "--source-id",
        required=True,
        type=UUID,
        help="UUID of an active row in public.sources.",
    )
    match = subcommands.add_parser(
        "match",
        help="Evaluate and persist all open jobs for one user's preferences.",
    )
    match.add_argument(
        "--user-id",
        required=True,
        type=UUID,
        help="Supabase Auth user UUID whose jobs should be evaluated.",
    )
    cycle = subcommands.add_parser(
        "cycle",
        help="Run every due source, refresh matching, queue alerts, and deliver due email.",
    )
    cycle.add_argument(
        "--skip-email",
        action="store_true",
        help="Queue notifications without claiming or sending email (local verification only).",
    )
    cycle.add_argument(
        "--max-deliveries",
        type=int,
        default=100,
        help="Maximum email digests to process in this cycle (1-1000).",
    )
    deliver = subcommands.add_parser(
        "deliver",
        help="Deliver due notification digests without running discovery or matching.",
    )
    deliver.add_argument(
        "--max-deliveries",
        type=int,
        default=100,
        help="Maximum email digests to process (1-1000).",
    )
    return parser


def _notification_dispatcher(settings: Settings, client: DatabaseClient) -> NotificationDispatcher:
    """Construct email delivery only after the command explicitly needs it."""
    api_key, from_address, app_base_url = settings.require_email_delivery()
    return NotificationDispatcher(
        NotificationRepository(client),
        ResendEmailProvider(api_key),
        from_address=from_address,
        app_base_url=app_base_url,
        maximum_attempts=settings.notification_max_attempts,
    )


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run a worker command and return a process exit code."""
    arguments = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    logger = structlog.get_logger("launchpad.worker")
    if arguments.command == "deliver":
        try:
            client = create_database_client(settings)
            delivery_stats = _notification_dispatcher(settings, client).drain(
                maximum_deliveries=arguments.max_deliveries
            )
        except (NotificationPersistenceError, ValueError) as error:
            logger.error(
                "notification_delivery_failed",
                error_type=type(error).__name__,
                error_summary=str(error),
            )
            return 1
        logger.info(
            "notification_delivery_completed",
            claimed=delivery_stats.claimed,
            sent=delivery_stats.sent,
            retry_scheduled=delivery_stats.retry_scheduled,
            permanently_failed=delivery_stats.permanently_failed,
        )
        return 1 if delivery_stats.retry_scheduled or delivery_stats.permanently_failed else 0

    if arguments.command == "cycle":
        try:
            client = create_database_client(settings)
            dispatcher = (
                None if arguments.skip_email else _notification_dispatcher(settings, client)
            )
            cycle_stats = AutomationRunner(
                AutomationRepository(client),
                ConfiguredSourceOperation(client),
                ConfiguredMatchingOperation(client),
                NotificationRepository(client),
                dispatcher=dispatcher,
            ).run(maximum_deliveries=arguments.max_deliveries)
        except (
            AutomationPersistenceError,
            NotificationPersistenceError,
            ValueError,
        ) as error:
            logger.error(
                "automation_cycle_failed",
                error_type=type(error).__name__,
                error_summary=str(error),
            )
            return 1
        logger.info(
            "automation_cycle_completed",
            sources_attempted=cycle_stats.sources_attempted,
            sources_succeeded=cycle_stats.sources_succeeded,
            sources_failed=cycle_stats.sources_failed,
            users_attempted=cycle_stats.users_attempted,
            users_succeeded=cycle_stats.users_succeeded,
            users_failed=cycle_stats.users_failed,
            notifications_queued=cycle_stats.notifications_queued,
            delivery_claimed=cycle_stats.delivery.claimed if cycle_stats.delivery else 0,
            delivery_sent=cycle_stats.delivery.sent if cycle_stats.delivery else 0,
            delivery_retry_scheduled=(
                cycle_stats.delivery.retry_scheduled if cycle_stats.delivery else 0
            ),
            delivery_permanently_failed=(
                cycle_stats.delivery.permanently_failed if cycle_stats.delivery else 0
            ),
        )
        return 1 if cycle_stats.has_failures else 0

    if arguments.command == "match":
        user_id = str(arguments.user_id)
        try:
            client = create_database_client(settings)
            logger.info("matching_started", user_id=user_id)
            matching_stats = MatchingRunner(MatchingRepository(client)).run(user_id)
        except MatchingPersistenceError as error:
            logger.error(
                "matching_operation_failed",
                user_id=user_id,
                error_type=type(error).__name__,
                error_summary=str(error),
            )
            return 1

        logger.info(
            "matching_completed",
            user_id=user_id,
            evaluated=matching_stats.evaluated,
            matched=matching_stats.matched,
            review=matching_stats.review,
            rejected=matching_stats.rejected,
        )
        return 0

    source_id = str(arguments.source_id)

    try:
        client = create_database_client(settings)
        configured = SourceRegistry(cast(TableClient, client)).get(source_id)
        source = build_job_source(configured)
        logger.info(
            "discovery_started",
            source_id=source_id,
            source_type=configured.source_type,
        )
        discovery_stats = DiscoveryRunner(DiscoveryRepository(client)).run(
            source_id=source_id,
            source=source,
        )
    except SourceFetchError as error:
        logger.error(
            "discovery_source_failed",
            source_id=source_id,
            source_type=error.source_type,
            error_code=error.error_code,
        )
        return 1
    except (DiscoveryPersistenceError, SourceRegistryError) as error:
        logger.error(
            "discovery_operation_failed",
            source_id=source_id,
            error_type=type(error).__name__,
            error_summary=str(error),
        )
        return 1

    logger.info(
        "discovery_completed",
        source_id=source_id,
        source_check_id=discovery_stats.source_check_id,
        inserted=discovery_stats.inserted,
        updated=discovery_stats.updated,
        unchanged=discovery_stats.unchanged,
        reopened=discovery_stats.reopened,
    )
    return 0


def main() -> None:
    """Run the CLI as an installed console script."""
    raise SystemExit(run_cli())
