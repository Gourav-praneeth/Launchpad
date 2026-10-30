"""Command-line interface for operational worker runs."""

import argparse
from collections.abc import Sequence
from typing import cast
from uuid import UUID

import structlog

from launchpad_worker.config import get_settings
from launchpad_worker.database import create_database_client
from launchpad_worker.discovery import DiscoveryRunner
from launchpad_worker.logging import configure_logging
from launchpad_worker.matching_persistence import (
    MatchingPersistenceError,
    MatchingRepository,
    MatchingRunner,
)
from launchpad_worker.persistence import DiscoveryPersistenceError, DiscoveryRepository
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
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run a worker command and return a process exit code."""
    arguments = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    logger = structlog.get_logger("launchpad.worker")
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
