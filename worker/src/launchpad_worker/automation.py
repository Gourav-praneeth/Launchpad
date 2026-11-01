"""Fault-isolated orchestration for scheduled discovery, matching, and alerts."""

from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID

import structlog

from launchpad_worker.discovery import DiscoveryRunner
from launchpad_worker.matching_persistence import (
    MatchingPersistenceError,
    MatchingRepository,
    MatchingRunner,
)
from launchpad_worker.notifications import (
    DispatchStats,
    NotificationDispatcher,
    NotificationPersistenceError,
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


class AutomationPersistenceError(RuntimeError):
    """Automation targets could not be loaded safely."""


@dataclass(frozen=True, slots=True)
class AutomationTargets:
    """Sources currently due and users whose open jobs require matching."""

    source_ids: tuple[str, ...]
    user_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AutomationStats:
    """Aggregate outcomes from one fault-isolated scheduled cycle."""

    sources_attempted: int
    sources_succeeded: int
    sources_failed: int
    users_attempted: int
    users_succeeded: int
    users_failed: int
    notifications_queued: int
    delivery: DispatchStats | None

    @property
    def has_failures(self) -> bool:
        return (
            self.sources_failed > 0
            or self.users_failed > 0
            or (
                self.delivery is not None
                and (self.delivery.retry_scheduled > 0 or self.delivery.permanently_failed > 0)
            )
        )


class AutomationTargetsStore(Protocol):
    def load(self) -> AutomationTargets: ...


class SourceOperation(Protocol):
    def run(self, source_id: str) -> None: ...


class MatchingOperation(Protocol):
    def run(self, user_id: str) -> None: ...


class NotificationQueueOperation(Protocol):
    def queue_for_user(self, user_id: str) -> Any: ...


class AutomationRepository:
    """Load a consistent list of currently eligible scheduled work."""

    def __init__(self, client: DatabaseClient) -> None:
        self._client = client

    def load(self) -> AutomationTargets:
        try:
            response = self._client.rpc("get_automation_targets", {}).execute()
            data = response.data
            if not isinstance(data, dict):
                raise TypeError("database returned a non-object target list")
            return AutomationTargets(
                source_ids=self._uuid_array(data, "source_ids"),
                user_ids=self._uuid_array(data, "user_ids"),
            )
        except AutomationPersistenceError:
            raise
        except Exception as error:
            raise AutomationPersistenceError("Database automation target load failed") from error

    @staticmethod
    def _uuid_array(data: dict[str, Any], key: str) -> tuple[str, ...]:
        value = data.get(key)
        if not isinstance(value, list):
            raise AutomationPersistenceError(f"Database returned invalid {key}")
        try:
            normalized = tuple(str(UUID(item)) for item in value)
        except (AttributeError, TypeError, ValueError) as error:
            raise AutomationPersistenceError(f"Database returned invalid {key}") from error
        if len(set(normalized)) != len(normalized):
            raise AutomationPersistenceError(f"Database returned duplicate {key}")
        return normalized


class ConfiguredSourceOperation:
    """Resolve and run one database-configured source."""

    def __init__(self, client: DatabaseClient) -> None:
        self._registry = SourceRegistry(cast(TableClient, client))
        self._runner = DiscoveryRunner(DiscoveryRepository(client))

    def run(self, source_id: str) -> None:
        configured = self._registry.get(source_id)
        self._runner.run(source_id=source_id, source=build_job_source(configured))


class ConfiguredMatchingOperation:
    """Evaluate and persist one user's complete deterministic snapshot."""

    def __init__(self, client: DatabaseClient) -> None:
        self._runner = MatchingRunner(MatchingRepository(client))

    def run(self, user_id: str) -> None:
        self._runner.run(user_id)


class AutomationRunner:
    """Continue independent work after partial source or user failures."""

    def __init__(
        self,
        targets: AutomationTargetsStore,
        sources: SourceOperation,
        matching: MatchingOperation,
        notifications: NotificationQueueOperation,
        *,
        dispatcher: NotificationDispatcher | None = None,
    ) -> None:
        self._targets = targets
        self._sources = sources
        self._matching = matching
        self._notifications = notifications
        self._dispatcher = dispatcher
        self._logger = structlog.get_logger("launchpad.automation")

    def run(self, *, maximum_deliveries: int = 100) -> AutomationStats:
        """Run every due source and user without turning one failure into a global outage."""
        targets = self._targets.load()
        sources_succeeded = sources_failed = 0
        users_succeeded = users_failed = notifications_queued = 0

        for source_id in targets.source_ids:
            try:
                self._sources.run(source_id)
            except (SourceFetchError, DiscoveryPersistenceError, SourceRegistryError) as error:
                sources_failed += 1
                self._logger.error(
                    "scheduled_source_failed",
                    source_id=source_id,
                    error_type=type(error).__name__,
                    error_summary=str(error),
                )
            else:
                sources_succeeded += 1

        for user_id in targets.user_ids:
            try:
                self._matching.run(user_id)
                queued = self._notifications.queue_for_user(user_id)
                notifications_queued += int(queued.queued)
            except (MatchingPersistenceError, NotificationPersistenceError) as error:
                users_failed += 1
                self._logger.error(
                    "scheduled_user_failed",
                    user_id=user_id,
                    error_type=type(error).__name__,
                    error_summary=str(error),
                )
            else:
                users_succeeded += 1

        delivery = (
            self._dispatcher.drain(maximum_deliveries=maximum_deliveries)
            if self._dispatcher is not None
            else None
        )
        return AutomationStats(
            sources_attempted=len(targets.source_ids),
            sources_succeeded=sources_succeeded,
            sources_failed=sources_failed,
            users_attempted=len(targets.user_ids),
            users_succeeded=users_succeeded,
            users_failed=users_failed,
            notifications_queued=notifications_queued,
            delivery=delivery,
        )
