"""Command-line entry point for the worker foundation."""

import structlog

from launchpad_worker import __version__
from launchpad_worker.config import get_settings
from launchpad_worker.logging import configure_logging


def main() -> None:
    """Validate configuration and report that the Phase 1 worker is ready."""
    settings = get_settings()
    configure_logging(settings)
    logger = structlog.get_logger("launchpad.worker")
    logger.info("worker_foundation_ready", version=__version__)


if __name__ == "__main__":
    main()
