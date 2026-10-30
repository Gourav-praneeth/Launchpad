"""Tests for the single-source discovery workflow."""

from datetime import UTC, datetime
from typing import Any

import pytest

from launchpad_worker.discovery import DiscoveryRunner
from launchpad_worker.models import SourceFetchResult
from launchpad_worker.persistence import PersistenceStats
from launchpad_worker.sources import JobSource, SourceFetchError

STARTED_AT = datetime(2026, 10, 30, 18, 29, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 10, 30, 18, 30, tzinfo=UTC)
STATS = PersistenceStats(
    source_check_id="check-123",
    inserted=0,
    updated=0,
    unchanged=0,
    reopened=0,
)


class SuccessfulSource(JobSource):
    source_type = "fixture"

    def fetch_jobs(self) -> SourceFetchResult:
        return SourceFetchResult(jobs=(), issues=(), fetched_at=COMPLETED_AT)


class FailingSource(JobSource):
    source_type = "fixture"

    def fetch_jobs(self) -> SourceFetchResult:
        raise SourceFetchError(
            source_type=self.source_type,
            error_code="request_failed",
            message="Fixture request failed: ReadTimeout",
        )


class FakeStore:
    def __init__(self) -> None:
        self.fetch_arguments: dict[str, Any] | None = None
        self.failure_arguments: dict[str, Any] | None = None

    def persist_fetch(
        self,
        *,
        source_id: str,
        started_at: datetime,
        result: SourceFetchResult,
    ) -> PersistenceStats:
        self.fetch_arguments = {
            "source_id": source_id,
            "started_at": started_at,
            "result": result,
        }
        return STATS

    def record_failure(
        self,
        *,
        source_id: str,
        started_at: datetime,
        completed_at: datetime,
        error_code: str,
        error_summary: str,
        http_status: int | None = None,
    ) -> PersistenceStats:
        self.failure_arguments = {
            "source_id": source_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "error_code": error_code,
            "error_summary": error_summary,
            "http_status": http_status,
        }
        return STATS


def test_successful_run_persists_fetch_result() -> None:
    store = FakeStore()
    runner = DiscoveryRunner(store, clock=lambda: STARTED_AT)

    stats = runner.run(source_id="source-123", source=SuccessfulSource())

    assert stats == STATS
    assert store.failure_arguments is None
    assert store.fetch_arguments == {
        "source_id": "source-123",
        "started_at": STARTED_AT,
        "result": SourceFetchResult(jobs=(), issues=(), fetched_at=COMPLETED_AT),
    }


def test_failed_run_is_recorded_and_remains_failed() -> None:
    store = FakeStore()
    times = iter((STARTED_AT, COMPLETED_AT))
    runner = DiscoveryRunner(store, clock=lambda: next(times))

    with pytest.raises(SourceFetchError, match="ReadTimeout"):
        runner.run(source_id="source-123", source=FailingSource())

    assert store.fetch_arguments is None
    assert store.failure_arguments == {
        "source_id": "source-123",
        "started_at": STARTED_AT,
        "completed_at": COMPLETED_AT,
        "error_code": "request_failed",
        "error_summary": "Fixture request failed: ReadTimeout",
        "http_status": None,
    }
