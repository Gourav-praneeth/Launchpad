"""Orchestration for one observable, persistence-safe discovery run."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from launchpad_worker.models import SourceFetchResult
from launchpad_worker.persistence import PersistenceStats
from launchpad_worker.sources import JobSource, SourceFetchError


class DiscoveryStore(Protocol):
    def persist_fetch(
        self,
        *,
        source_id: str,
        started_at: datetime,
        result: SourceFetchResult,
    ) -> PersistenceStats: ...

    def record_failure(
        self,
        *,
        source_id: str,
        started_at: datetime,
        completed_at: datetime,
        error_code: str,
        error_summary: str,
        http_status: int | None = None,
    ) -> PersistenceStats: ...


class DiscoveryRunner:
    """Fetch one source and persist either its result or its safe failure details."""

    def __init__(
        self,
        store: DiscoveryStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self, *, source_id: str, source: JobSource) -> PersistenceStats:
        """Run one source check while keeping failed checks observable."""
        started_at = self._clock()
        try:
            result = source.fetch_jobs()
        except SourceFetchError as error:
            self._store.record_failure(
                source_id=source_id,
                started_at=started_at,
                completed_at=self._clock(),
                error_code=error.error_code,
                error_summary=str(error),
            )
            raise

        return self._store.persist_fetch(
            source_id=source_id,
            started_at=started_at,
            result=result,
        )
