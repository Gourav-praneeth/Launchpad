"""Tests for atomic discovery persistence payloads."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import pytest

from launchpad_worker.models import JobListing, SourceFetchResult, SourceItemIssue
from launchpad_worker.persistence import (
    DiscoveryPersistenceError,
    DiscoveryRepository,
)

STARTED_AT = datetime(2026, 10, 30, 18, 29, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 10, 30, 18, 30, tzinfo=UTC)


@dataclass
class FakeResponse:
    data: Any


class FakeRequest:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def execute(self) -> FakeResponse:
        return self.response


class FakeClient:
    def __init__(self, data: Any | None = None) -> None:
        self.data = data or {
            "source_check_id": "check-123",
            "inserted": 1,
            "updated": 0,
            "unchanged": 0,
            "reopened": 0,
        }
        self.function_name: str | None = None
        self.params: dict[str, Any] | None = None

    def rpc(self, fn: str, params: dict[str, Any]) -> FakeRequest:
        self.function_name = fn
        self.params = params
        return FakeRequest(FakeResponse(self.data))


def make_listing() -> JobListing:
    return JobListing(
        external_id="127817",
        dedupe_key="external:127817",
        title=" Software  Engineer, New Grad ",
        location="San Francisco, CA",
        apply_url="https://careers.example.test/jobs?gh_jid=127817&utm_source=test",
        canonical_apply_url="https://careers.example.test/jobs?gh_jid=127817",
        employer_posted_at=None,
        source_updated_at=datetime(2026, 10, 29, 23, 45, 12, tzinfo=UTC),
        description="Build dependable systems.",
    )


def test_persist_fetch_builds_atomic_rpc_payload() -> None:
    client = FakeClient()
    repository = DiscoveryRepository(client)

    stats = repository.persist_fetch(
        source_id="source-123",
        started_at=STARTED_AT,
        result=SourceFetchResult(jobs=(make_listing(),), issues=(), fetched_at=COMPLETED_AT),
    )

    assert stats.source_check_id == "check-123"
    assert stats.inserted == 1
    assert client.function_name == "persist_discovery_check"
    assert client.params is not None
    assert client.params["p_outcome"] == "successful"
    assert client.params["p_listings_fetched"] == 1
    assert client.params["p_error_code"] is None
    listing = client.params["p_listings"][0]
    assert listing["external_job_id"] == "127817"
    assert listing["normalized_title"] == "software engineer, new grad"
    assert listing["employer_posted_at"] is None
    assert listing["source_updated_at"] == "2026-10-29T23:45:12+00:00"
    assert len(listing["content_hash"]) == 64


def test_partial_fetch_records_rejections_without_exposing_issue_content() -> None:
    client = FakeClient()
    repository = DiscoveryRepository(client)
    issue = SourceItemIssue(
        item_index=1,
        external_id="bad-job",
        error_code="invalid_job",
        message="Invalid title",
    )

    repository.persist_fetch(
        source_id="source-123",
        started_at=STARTED_AT,
        result=SourceFetchResult(jobs=(make_listing(),), issues=(issue,), fetched_at=COMPLETED_AT),
    )

    assert client.params is not None
    assert client.params["p_outcome"] == "partial"
    assert client.params["p_listings_fetched"] == 2
    assert client.params["p_error_code"] == "invalid_items"
    assert client.params["p_error_summary"] == ("Rejected 1 of 2 source items during validation")
    assert "Invalid title" not in str(client.params)


def test_record_failure_sends_no_listings() -> None:
    client = FakeClient(
        {
            "source_check_id": "failed-check",
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "reopened": 0,
        }
    )
    repository = DiscoveryRepository(client)

    stats = repository.record_failure(
        source_id="source-123",
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        error_code="request_failed",
        error_summary="Greenhouse request failed: ReadTimeout",
    )

    assert stats.source_check_id == "failed-check"
    assert client.params is not None
    assert client.params["p_outcome"] == "failed"
    assert client.params["p_listings"] == []
    assert client.params["p_listings_fetched"] == 0


def test_content_hash_is_deterministic_and_excludes_source_timestamp() -> None:
    first = DiscoveryRepository._serialize_listing(make_listing())
    changed_timestamp = replace(
        make_listing(),
        source_updated_at=datetime(2026, 10, 30, 1, 2, tzinfo=UTC),
    )
    second = DiscoveryRepository._serialize_listing(changed_timestamp)

    assert first["content_hash"] == second["content_hash"]


def test_content_hash_excludes_identity_but_tracks_visible_changes() -> None:
    original = make_listing()
    changed_identity = replace(
        original,
        external_id="different-id",
        dedupe_key="external:different-id",
    )
    changed_title = replace(original, title="Software Engineer I")

    original_hash = DiscoveryRepository._serialize_listing(original)["content_hash"]

    assert DiscoveryRepository._serialize_listing(changed_identity)["content_hash"] == original_hash
    assert DiscoveryRepository._serialize_listing(changed_title)["content_hash"] != original_hash


def test_rejects_naive_or_reversed_timestamps() -> None:
    repository = DiscoveryRepository(FakeClient())
    result = SourceFetchResult(jobs=(), issues=(), fetched_at=STARTED_AT)

    with pytest.raises(ValueError, match="timezone-aware"):
        repository.persist_fetch(
            source_id="source-123",
            started_at=STARTED_AT.replace(tzinfo=None),
            result=result,
        )

    with pytest.raises(ValueError, match="cannot precede"):
        repository.persist_fetch(
            source_id="source-123",
            started_at=COMPLETED_AT,
            result=result,
        )


def test_rejects_invalid_database_result() -> None:
    repository = DiscoveryRepository(FakeClient({"inserted": "one"}))

    with pytest.raises(DiscoveryPersistenceError, match="source_check_id"):
        repository.persist_fetch(
            source_id="source-123",
            started_at=STARTED_AT,
            result=SourceFetchResult(jobs=(), issues=(), fetched_at=COMPLETED_AT),
        )
