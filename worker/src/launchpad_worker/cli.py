"""Command-line interface for operational discovery runs."""

import argparse
from collections.abc import Sequence
from typing import cast
from uuid import UUID

import structlog

from launchpad_worker.config import get_settings
from launchpad_worker.database import create_database_client
from launchpad_worker.discovery import DiscoveryRunner
from launchpad_worker.logging import configure_logging
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
        description="Run Launchpad discovery operations.",
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
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run a worker command and return a process exit code."""
    arguments = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    logger = structlog.get_logger("launchpad.worker")
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
        stats = DiscoveryRunner(DiscoveryRepository(client)).run(
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
        source_check_id=stats.source_check_id,
        inserted=stats.inserted,
        updated=stats.updated,
        unchanged=stats.unchanged,
        reopened=stats.reopened,
    )
    return 0


def main() -> None:
    """Run the CLI as an installed console script."""
    raise SystemExit(run_cli())
