"""Atomic loading and persistence for deterministic user/job matching."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from launchpad_worker.matching import (
    CareerLevel,
    JobMatcher,
    JobPreferences,
    MatchReason,
    MatchResult,
    SponsorshipPreference,
)
from launchpad_worker.models import JobListing
from launchpad_worker.persistence import DatabaseClient

MATCHER_VERSION = "deterministic-v1"


class MatchingPersistenceError(RuntimeError):
    """Matching context or results could not be safely persisted."""


@dataclass(frozen=True, slots=True)
class MatchingCandidate:
    """One database job plus the content token used for stale-write protection."""

    job_id: str
    content_hash: str
    listing: JobListing


@dataclass(frozen=True, slots=True)
class MatchingContext:
    """One consistent preference snapshot and its open candidate jobs."""

    user_id: str
    preference_id: str
    preference_updated_at: datetime
    preferences: JobPreferences
    candidates: tuple[MatchingCandidate, ...]


@dataclass(frozen=True, slots=True)
class EvaluatedCandidate:
    """A candidate paired with its pure deterministic decision."""

    candidate: MatchingCandidate
    result: MatchResult


@dataclass(frozen=True, slots=True)
class MatchingStats:
    """Counts committed by the atomic result transaction."""

    evaluated: int
    matched: int
    review: int
    rejected: int


class MatchingRepository:
    """Load match inputs and atomically store a complete evaluated snapshot."""

    context_rpc = "get_matching_context"
    persistence_rpc = "persist_job_match_results"

    def __init__(self, client: DatabaseClient) -> None:
        self._client = client

    def load_context(self, user_id: str) -> MatchingContext:
        """Load one user's preferences and every currently open owned job."""
        normalized_user_id = self._required_uuid(user_id, "user_id")
        data = self._call_rpc(self.context_rpc, {"p_user_id": normalized_user_id})
        preference = self._required_object(data, "preference")
        jobs = self._required_array(data, "jobs")

        try:
            preferences = JobPreferences(
                target_titles=self._string_array(preference, "target_titles"),
                career_levels=tuple(
                    CareerLevel(value) for value in self._string_array(preference, "career_levels")
                ),
                employment_types=self._string_array(preference, "employment_types"),
                locations=self._string_array(preference, "locations"),
                workplace_types=self._string_array(preference, "workplace_types"),
                include_keywords=self._string_array(preference, "include_keywords"),
                exclude_keywords=self._string_array(preference, "exclude_keywords"),
                sponsorship_preference=SponsorshipPreference(
                    self._required_string(preference, "sponsorship_preference")
                ),
                include_senior_roles=self._required_boolean(preference, "include_senior_roles"),
            )
            candidates = tuple(self._parse_candidate(row) for row in jobs)
        except (TypeError, ValueError) as error:
            raise MatchingPersistenceError("Database returned invalid matching context") from error

        candidate_ids = {candidate.job_id for candidate in candidates}
        if len(candidate_ids) != len(candidates):
            raise MatchingPersistenceError("Database returned duplicate matching candidates")

        return MatchingContext(
            user_id=normalized_user_id,
            preference_id=self._required_uuid(
                self._required_string(preference, "id"), "preference.id"
            ),
            preference_updated_at=self._required_datetime(preference, "updated_at"),
            preferences=preferences,
            candidates=candidates,
        )

    def persist_results(
        self,
        context: MatchingContext,
        evaluated: tuple[EvaluatedCandidate, ...],
    ) -> MatchingStats:
        """Atomically replace a user's results for the exact loaded snapshot."""
        expected_ids = {candidate.job_id for candidate in context.candidates}
        actual_ids = {item.candidate.job_id for item in evaluated}
        if len(evaluated) != len(context.candidates) or actual_ids != expected_ids:
            raise ValueError("evaluated results must cover every matching candidate exactly once")

        results = [self._serialize_evaluated(item) for item in evaluated]
        data = self._call_rpc(
            self.persistence_rpc,
            {
                "p_user_id": context.user_id,
                "p_preference_updated_at": context.preference_updated_at.isoformat(),
                "p_matcher_version": MATCHER_VERSION,
                "p_results": results,
            },
        )
        stats = MatchingStats(
            evaluated=self._required_count(data, "evaluated"),
            matched=self._required_count(data, "matched"),
            review=self._required_count(data, "review"),
            rejected=self._required_count(data, "rejected"),
        )
        if stats.evaluated != len(evaluated):
            raise MatchingPersistenceError("Database returned an incorrect evaluated count")
        if stats.matched + stats.review + stats.rejected != stats.evaluated:
            raise MatchingPersistenceError("Database returned inconsistent matching counts")
        return stats

    def _call_rpc(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.rpc(name, params).execute()
            if not isinstance(response.data, dict):
                raise TypeError("database returned a non-object result")
            return response.data
        except MatchingPersistenceError:
            raise
        except Exception as error:
            raise MatchingPersistenceError("Database matching transaction failed") from error

    @classmethod
    def _parse_candidate(cls, value: Any) -> MatchingCandidate:
        if not isinstance(value, dict):
            raise TypeError("candidate must be an object")
        job_id = cls._required_uuid(cls._required_string(value, "id"), "job.id")
        return MatchingCandidate(
            job_id=job_id,
            content_hash=cls._required_string(value, "content_hash"),
            listing=JobListing(
                external_id=cls._optional_string(value, "external_job_id"),
                dedupe_key=cls._required_string(value, "dedupe_key"),
                title=cls._required_string(value, "title"),
                location=cls._optional_string(value, "location"),
                apply_url=cls._required_string(value, "apply_url"),
                canonical_apply_url=cls._required_string(value, "canonical_apply_url"),
                employer_posted_at=cls._optional_datetime(value, "employer_posted_at"),
                source_updated_at=cls._optional_datetime(value, "source_updated_at"),
                description=cls._optional_string(value, "description"),
                employment_type=cls._optional_string(value, "employment_type"),
                workplace_type=cls._optional_string(value, "workplace_type"),
            ),
        )

    @classmethod
    def _serialize_evaluated(cls, item: EvaluatedCandidate) -> dict[str, Any]:
        return {
            "job_id": item.candidate.job_id,
            "job_content_hash": item.candidate.content_hash,
            "status": item.result.status.value,
            "career_level": item.result.career_level.value,
            "sponsorship_status": item.result.sponsorship_status.value,
            "match_reasons": cls._serialize_reasons(item.result.match_reasons),
            "review_reasons": cls._serialize_reasons(item.result.review_reasons),
            "rejection_reasons": cls._serialize_reasons(item.result.rejection_reasons),
        }

    @staticmethod
    def _serialize_reasons(reasons: tuple[MatchReason, ...]) -> list[dict[str, Any]]:
        return [
            {
                "code": reason.code,
                "message": reason.message,
                "evidence": list(reason.evidence),
            }
            for reason in reasons
        ]

    @staticmethod
    def _required_object(data: dict[str, Any], key: str) -> dict[str, Any]:
        value = data.get(key)
        if not isinstance(value, dict):
            raise MatchingPersistenceError(f"Database result has an invalid {key}")
        return value

    @staticmethod
    def _required_array(data: dict[str, Any], key: str) -> list[Any]:
        value = data.get(key)
        if not isinstance(value, list):
            raise MatchingPersistenceError(f"Database result has an invalid {key}")
        return value

    @staticmethod
    def _required_string(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise MatchingPersistenceError(f"Database result has an invalid {key}")
        return value.strip()

    @classmethod
    def _optional_string(cls, data: dict[str, Any], key: str) -> str | None:
        value = data.get(key)
        if value is None:
            return None
        return cls._required_string(data, key)

    @staticmethod
    def _required_boolean(data: dict[str, Any], key: str) -> bool:
        value = data.get(key)
        if not isinstance(value, bool):
            raise MatchingPersistenceError(f"Database result has an invalid {key}")
        return value

    @classmethod
    def _string_array(cls, data: dict[str, Any], key: str) -> tuple[str, ...]:
        values = cls._required_array(data, key)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise MatchingPersistenceError(f"Database result has an invalid {key}")
        return tuple(value.strip() for value in values)

    @staticmethod
    def _required_datetime(data: dict[str, Any], key: str) -> datetime:
        value = data.get(key)
        if not isinstance(value, str):
            raise MatchingPersistenceError(f"Database result has an invalid {key}")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise MatchingPersistenceError(f"Database result has an invalid {key}") from error
        if parsed.tzinfo is None:
            raise MatchingPersistenceError(f"Database result has a naive {key}")
        return parsed

    @classmethod
    def _optional_datetime(cls, data: dict[str, Any], key: str) -> datetime | None:
        if data.get(key) is None:
            return None
        return cls._required_datetime(data, key)

    @staticmethod
    def _required_uuid(value: str, name: str) -> str:
        try:
            return str(UUID(value))
        except (AttributeError, TypeError, ValueError) as error:
            raise MatchingPersistenceError(f"Database result has an invalid {name}") from error

    @staticmethod
    def _required_count(data: dict[str, Any], key: str) -> int:
        value = data.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise MatchingPersistenceError(f"Database result has an invalid {key} count")
        return value


class MatchingRunner:
    """Evaluate and persist one user's complete open-job snapshot."""

    def __init__(
        self,
        repository: MatchingRepository,
        matcher: JobMatcher | None = None,
    ) -> None:
        self._repository = repository
        self._matcher = matcher or JobMatcher()

    def run(self, user_id: str) -> MatchingStats:
        """Load, evaluate, and atomically store deterministic match results."""
        context = self._repository.load_context(user_id)
        evaluated = tuple(
            EvaluatedCandidate(
                candidate=candidate,
                result=self._matcher.evaluate(candidate.listing, context.preferences),
            )
            for candidate in context.candidates
        )
        return self._repository.persist_results(context, evaluated)
