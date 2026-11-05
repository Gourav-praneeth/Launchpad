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
MATCHING_PAGE_SIZE = 100


class MatchingPersistenceError(RuntimeError):
    """Matching context or results could not be safely persisted."""


@dataclass(frozen=True, slots=True)
class MatchingCandidate:
    """One database job plus the content token used for stale-write protection."""

    job_id: str
    content_hash: str
    listing: JobListing


@dataclass(frozen=True, slots=True)
class MatchingContextPage:
    """One bounded page from a consistent preference snapshot."""

    user_id: str
    preference_id: str
    preference_updated_at: datetime
    preferences: JobPreferences
    candidates: tuple[MatchingCandidate, ...]
    next_cursor: str | None
    has_more: bool


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
    """Load and persist bounded pages of stale deterministic match inputs."""

    context_rpc = "get_matching_context_page"
    persistence_rpc = "persist_job_match_results_page"
    finalize_rpc = "finalize_job_match_results"

    def __init__(self, client: DatabaseClient) -> None:
        self._client = client

    def load_page(
        self,
        user_id: str,
        *,
        after_job_id: str | None = None,
        page_size: int = MATCHING_PAGE_SIZE,
    ) -> MatchingContextPage:
        """Load one bounded page of missing or stale owned-job matches."""
        normalized_user_id = self._required_uuid(user_id, "user_id")
        normalized_cursor = (
            self._required_uuid(after_job_id, "after_job_id") if after_job_id is not None else None
        )
        if page_size < 1 or page_size > 250:
            raise ValueError("page_size must be between 1 and 250")
        data = self._call_rpc(
            self.context_rpc,
            {
                "p_user_id": normalized_user_id,
                "p_after_job_id": normalized_cursor,
                "p_limit": page_size,
                "p_matcher_version": MATCHER_VERSION,
            },
        )
        preference = self._required_object(data, "preference")
        jobs = self._required_array(data, "jobs")

        try:
            preferences = self._parse_preferences(preference)
            candidates = tuple(self._parse_candidate(row) for row in jobs)
        except (TypeError, ValueError) as error:
            raise MatchingPersistenceError("Database returned invalid matching context") from error

        candidate_ids = {candidate.job_id for candidate in candidates}
        if len(candidate_ids) != len(candidates):
            raise MatchingPersistenceError("Database returned duplicate matching candidates")

        ordered_ids = [UUID(candidate.job_id) for candidate in candidates]
        if ordered_ids != sorted(ordered_ids):
            raise MatchingPersistenceError("Database returned unordered matching candidates")
        if normalized_cursor is not None and any(
            job_id <= UUID(normalized_cursor) for job_id in ordered_ids
        ):
            raise MatchingPersistenceError("Database returned an invalid matching cursor page")

        has_more = self._required_boolean(data, "has_more")
        next_cursor_value = data.get("next_cursor")
        next_cursor = (
            self._required_uuid(next_cursor_value, "next_cursor")
            if next_cursor_value is not None
            else None
        )
        if has_more and (not candidates or next_cursor != candidates[-1].job_id):
            raise MatchingPersistenceError("Database returned an invalid next matching cursor")
        if not has_more and next_cursor is not None:
            raise MatchingPersistenceError("Database returned an unexpected next matching cursor")

        return MatchingContextPage(
            user_id=normalized_user_id,
            preference_id=self._required_uuid(
                self._required_string(preference, "id"), "preference.id"
            ),
            preference_updated_at=self._required_datetime(preference, "updated_at"),
            preferences=preferences,
            candidates=candidates,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    def persist_page(
        self,
        context: MatchingContextPage,
        evaluated: tuple[EvaluatedCandidate, ...],
    ) -> MatchingStats:
        """Atomically upsert one exact evaluated page with stale-write protection."""
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

    def finalize(self, context: MatchingContextPage) -> None:
        """Verify that no stale candidates remain and remove unavailable-job matches."""
        self._call_rpc(
            self.finalize_rpc,
            {
                "p_user_id": context.user_id,
                "p_preference_updated_at": context.preference_updated_at.isoformat(),
                "p_matcher_version": MATCHER_VERSION,
            },
        )

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
    def _parse_preferences(cls, preference: dict[str, Any]) -> JobPreferences:
        return JobPreferences(
            target_titles=cls._string_array(preference, "target_titles"),
            career_levels=tuple(
                CareerLevel(value) for value in cls._string_array(preference, "career_levels")
            ),
            employment_types=cls._string_array(preference, "employment_types"),
            locations=cls._string_array(preference, "locations"),
            workplace_types=cls._string_array(preference, "workplace_types"),
            include_keywords=cls._string_array(preference, "include_keywords"),
            exclude_keywords=cls._string_array(preference, "exclude_keywords"),
            sponsorship_preference=SponsorshipPreference(
                cls._required_string(preference, "sponsorship_preference")
            ),
            include_senior_roles=cls._required_boolean(preference, "include_senior_roles"),
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
    """Evaluate stale user/job matches in bounded, retry-safe pages."""

    def __init__(
        self,
        repository: MatchingRepository,
        matcher: JobMatcher | None = None,
    ) -> None:
        self._repository = repository
        self._matcher = matcher or JobMatcher()

    def run(self, user_id: str) -> MatchingStats:
        """Process all stale candidates, then verify the snapshot is complete."""
        cursor: str | None = None
        initial_context: MatchingContextPage | None = None
        seen_ids: set[str] = set()
        evaluated_count = matched_count = review_count = rejected_count = 0

        while True:
            context = self._repository.load_page(user_id, after_job_id=cursor)
            if initial_context is None:
                initial_context = context
            elif (
                context.preference_id != initial_context.preference_id
                or context.preference_updated_at != initial_context.preference_updated_at
                or context.preferences != initial_context.preferences
            ):
                raise MatchingPersistenceError("User preferences changed during paginated matching")

            page_ids = {candidate.job_id for candidate in context.candidates}
            if seen_ids & page_ids:
                raise MatchingPersistenceError("Database repeated a paginated matching candidate")
            seen_ids.update(page_ids)

            if context.candidates:
                evaluated = tuple(
                    EvaluatedCandidate(
                        candidate=candidate,
                        result=self._matcher.evaluate(candidate.listing, context.preferences),
                    )
                    for candidate in context.candidates
                )
                stats = self._repository.persist_page(context, evaluated)
                evaluated_count += stats.evaluated
                matched_count += stats.matched
                review_count += stats.review
                rejected_count += stats.rejected

            if not context.has_more:
                break
            cursor = context.next_cursor

        if initial_context is None:  # pragma: no cover - the loop always executes once
            raise MatchingPersistenceError("Database returned no matching context")
        self._repository.finalize(initial_context)
        return MatchingStats(
            evaluated=evaluated_count,
            matched=matched_count,
            review=review_count,
            rejected=rejected_count,
        )
