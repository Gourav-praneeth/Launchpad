"""Transaction-safe persistence for discovery outcomes."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from launchpad_worker.models import JobListing, SourceFetchResult


class _RpcResponse(Protocol):
    data: Any


class _RpcRequest(Protocol):
    def execute(self) -> _RpcResponse: ...


class DatabaseClient(Protocol):
    def rpc(self, fn: str, params: dict[str, Any]) -> _RpcRequest: ...


class DiscoveryPersistenceError(RuntimeError):
    """A discovery outcome could not be committed atomically."""


@dataclass(frozen=True, slots=True)
class PersistenceStats:
    """Counts returned by the database persistence transaction."""

    source_check_id: str
    inserted: int
    updated: int
    unchanged: int
    reopened: int


class DiscoveryRepository:
    """Persist fetch results through the database's atomic discovery RPC."""

    rpc_name = "persist_discovery_check"

    def __init__(self, client: DatabaseClient) -> None:
        self._client = client

    def persist_fetch(
        self,
        *,
        source_id: str,
        started_at: datetime,
        result: SourceFetchResult,
    ) -> PersistenceStats:
        """Persist every accepted listing and its source-check outcome once."""
        self._validate_time_range(started_at, result.fetched_at)
        outcome = "partial" if result.is_partial else "successful"
        issue_count = len(result.issues)
        return self._call_rpc(
            {
                "p_source_id": source_id,
                "p_started_at": started_at.isoformat(),
                "p_completed_at": result.fetched_at.isoformat(),
                "p_outcome": outcome,
                "p_listings": [self._serialize_listing(job) for job in result.jobs],
                "p_listings_fetched": len(result.jobs) + issue_count,
                "p_error_code": "invalid_items" if issue_count else None,
                "p_error_summary": self._issue_summary(issue_count, len(result.jobs)),
                "p_http_status": None,
            }
        )

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
        """Record a failed check without modifying any existing jobs."""
        self._validate_time_range(started_at, completed_at)
        if not error_code.strip() or not error_summary.strip():
            raise ValueError("failed source checks require an error code and summary")
        if http_status is not None and not 100 <= http_status <= 599:
            raise ValueError("HTTP status must be between 100 and 599")

        return self._call_rpc(
            {
                "p_source_id": source_id,
                "p_started_at": started_at.isoformat(),
                "p_completed_at": completed_at.isoformat(),
                "p_outcome": "failed",
                "p_listings": [],
                "p_listings_fetched": 0,
                "p_error_code": error_code.strip(),
                "p_error_summary": error_summary.strip(),
                "p_http_status": http_status,
            }
        )

    def _call_rpc(self, params: dict[str, Any]) -> PersistenceStats:
        try:
            response = self._client.rpc(self.rpc_name, params).execute()
            data = response.data
            if not isinstance(data, dict):
                raise TypeError("database returned a non-object result")
            return PersistenceStats(
                source_check_id=self._required_string(data, "source_check_id"),
                inserted=self._required_count(data, "inserted"),
                updated=self._required_count(data, "updated"),
                unchanged=self._required_count(data, "unchanged"),
                reopened=self._required_count(data, "reopened"),
            )
        except DiscoveryPersistenceError:
            raise
        except Exception as error:
            raise DiscoveryPersistenceError("Database discovery transaction failed") from error

    @classmethod
    def _serialize_listing(cls, listing: JobListing) -> dict[str, Any]:
        identity_fields = {
            "external_job_id": listing.external_id,
            "dedupe_key": listing.dedupe_key,
        }
        content_fields = {
            "title": listing.title,
            "normalized_title": " ".join(listing.title.split()).casefold(),
            "location": listing.location,
            "workplace_type": listing.workplace_type,
            "employment_type": listing.employment_type,
            "description": listing.description,
            "apply_url": listing.apply_url,
            "canonical_apply_url": listing.canonical_apply_url,
            "employer_posted_at": cls._serialize_datetime(listing.employer_posted_at),
        }
        content_json = json.dumps(
            content_fields,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            **identity_fields,
            **content_fields,
            "source_updated_at": cls._serialize_datetime(listing.source_updated_at),
            "content_hash": hashlib.sha256(content_json.encode("utf-8")).hexdigest(),
        }

    @staticmethod
    def _serialize_datetime(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _issue_summary(issue_count: int, accepted_count: int) -> str | None:
        if issue_count == 0:
            return None
        total = issue_count + accepted_count
        return f"Rejected {issue_count} of {total} source items during validation"

    @staticmethod
    def _validate_time_range(started_at: datetime, completed_at: datetime) -> None:
        if started_at.tzinfo is None or completed_at.tzinfo is None:
            raise ValueError("discovery timestamps must be timezone-aware")
        if completed_at < started_at:
            raise ValueError("discovery completion cannot precede its start")

    @staticmethod
    def _required_string(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise DiscoveryPersistenceError(f"Database result is missing {key}")
        return value

    @staticmethod
    def _required_count(data: dict[str, Any], key: str) -> int:
        value = data.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise DiscoveryPersistenceError(f"Database result has an invalid {key} count")
        return value
