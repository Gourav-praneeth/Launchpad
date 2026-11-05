from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

import pytest

from launchpad_worker.matching import JobMatcher
from launchpad_worker.matching_persistence import (
    EvaluatedCandidate,
    MatchingPersistenceError,
    MatchingRepository,
    MatchingRunner,
)

USER_ID = "10000000-0000-0000-0000-000000000001"
PREFERENCE_ID = "50000000-0000-0000-0000-000000000001"
FIRST_JOB_ID = "40000000-0000-0000-0000-000000000001"
SECOND_JOB_ID = "40000000-0000-0000-0000-000000000002"


@dataclass
class FakeResponse:
    data: Any


class FakeRequest:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response

    def execute(self) -> FakeResponse:
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, fn: str, params: dict[str, Any]) -> FakeRequest:
        self.calls.append((fn, params))
        response = self.responses[fn]
        if isinstance(response, list):
            response = response.pop(0)
        if isinstance(response, Exception):
            return FakeRequest(response)
        return FakeRequest(FakeResponse(response))


def job_row(
    *,
    job_id: str = FIRST_JOB_ID,
    title: str = "Software Engineer, New Grad",
    content_hash: str = "hash-1",
    employment_type: str | None = "full-time",
) -> dict[str, Any]:
    return {
        "id": job_id,
        "external_job_id": f"external-{job_id[-1]}",
        "dedupe_key": f"external:{job_id[-1]}",
        "title": title,
        "location": "San Francisco, CA",
        "workplace_type": "hybrid",
        "employment_type": employment_type,
        "description": "Build dependable backend services.",
        "apply_url": f"https://example.test/jobs/{job_id[-1]}",
        "canonical_apply_url": f"https://example.test/jobs/{job_id[-1]}",
        "employer_posted_at": None,
        "source_updated_at": "2026-10-30T10:00:00+00:00",
        "content_hash": content_hash,
    }


def context_response(
    *jobs: dict[str, Any],
    has_more: bool = False,
    next_cursor: str | None = None,
) -> dict[str, Any]:
    return {
        "preference": {
            "id": PREFERENCE_ID,
            "updated_at": "2026-10-30T10:05:00+00:00",
            "target_titles": [],
            "career_levels": ["new_grad", "entry_level", "early_career"],
            "employment_types": ["full-time"],
            "locations": [],
            "workplace_types": [],
            "include_keywords": [],
            "exclude_keywords": [],
            "sponsorship_preference": "any",
            "include_senior_roles": False,
        },
        "jobs": list(jobs),
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


def test_runner_evaluates_and_persists_paginated_snapshot() -> None:
    first = job_row()
    second = job_row(
        job_id=SECOND_JOB_ID,
        title="Software Engineer",
        content_hash="hash-2",
        employment_type=None,
    )
    client = FakeClient(
        {
            "get_matching_context_page": [
                context_response(first, has_more=True, next_cursor=FIRST_JOB_ID),
                context_response(second),
            ],
            "persist_job_match_results_page": [
                {"evaluated": 1, "matched": 1, "review": 0, "rejected": 0},
                {"evaluated": 1, "matched": 0, "review": 1, "rejected": 0},
            ],
            "finalize_job_match_results": {"removed": 0},
        }
    )

    stats = MatchingRunner(MatchingRepository(client)).run(USER_ID)

    assert stats.evaluated == 2
    assert stats.matched == 1
    assert stats.review == 1
    assert [call[0] for call in client.calls] == [
        "get_matching_context_page",
        "persist_job_match_results_page",
        "get_matching_context_page",
        "persist_job_match_results_page",
        "finalize_job_match_results",
    ]
    persistence_params = client.calls[1][1]
    assert persistence_params["p_user_id"] == USER_ID
    assert persistence_params["p_matcher_version"] == "deterministic-v1"
    assert persistence_params["p_preference_updated_at"] == ("2026-10-30T10:05:00+00:00")
    results = persistence_params["p_results"]
    assert results[0]["status"] == "matched"
    assert results[0]["job_content_hash"] == "hash-1"
    second_results = client.calls[3][1]["p_results"]
    assert second_results[0]["status"] == "review"
    assert {reason["code"] for reason in second_results[0]["review_reasons"]} == {
        "career_level_unknown",
        "employment_type_unknown",
    }
    assert client.calls[2][1]["p_after_job_id"] == FIRST_JOB_ID


def test_context_parses_typed_preferences_and_listing_timestamps() -> None:
    repository = MatchingRepository(
        FakeClient({"get_matching_context_page": context_response(job_row())})
    )

    context = repository.load_page(USER_ID)

    assert context.preference_id == PREFERENCE_ID
    assert context.preference_updated_at == datetime(2026, 10, 30, 10, 5, tzinfo=UTC)
    assert context.preferences.employment_types == ("full-time",)
    assert context.candidates[0].listing.source_updated_at == datetime(2026, 10, 30, 10, tzinfo=UTC)


def test_context_rejects_unsupported_preference_values() -> None:
    response = context_response(job_row())
    response["preference"]["career_levels"] = ["executive"]
    repository = MatchingRepository(FakeClient({"get_matching_context_page": response}))

    with pytest.raises(MatchingPersistenceError, match="invalid matching context"):
        repository.load_page(USER_ID)


def test_context_rejects_duplicate_candidates() -> None:
    duplicate = job_row()
    repository = MatchingRepository(
        FakeClient({"get_matching_context_page": context_response(duplicate, duplicate)})
    )

    with pytest.raises(MatchingPersistenceError, match="duplicate matching candidates"):
        repository.load_page(USER_ID)


def test_context_rejects_naive_or_invalid_timestamp() -> None:
    response = context_response(job_row())
    response["preference"]["updated_at"] = "2026-10-30T10:05:00"
    repository = MatchingRepository(FakeClient({"get_matching_context_page": response}))

    with pytest.raises(MatchingPersistenceError, match="naive updated_at"):
        repository.load_page(USER_ID)


def test_database_errors_are_safely_wrapped() -> None:
    repository = MatchingRepository(
        FakeClient({"get_matching_context_page": RuntimeError("sensitive database message")})
    )

    with pytest.raises(MatchingPersistenceError, match="Database matching transaction failed"):
        repository.load_page(USER_ID)


def test_persistence_requires_every_page_candidate_exactly_once() -> None:
    client = FakeClient({"get_matching_context_page": context_response(job_row())})
    repository = MatchingRepository(client)
    context = repository.load_page(USER_ID)

    with pytest.raises(ValueError, match="every matching candidate"):
        repository.persist_page(context, ())


def test_persistence_rejects_inconsistent_database_counts() -> None:
    client = FakeClient(
        {
            "get_matching_context_page": context_response(job_row()),
            "persist_job_match_results_page": {
                "evaluated": 1,
                "matched": 1,
                "review": 1,
                "rejected": 0,
            },
        }
    )
    repository = MatchingRepository(client)
    context = repository.load_page(USER_ID)
    candidate = context.candidates[0]
    result = JobMatcher().evaluate(candidate.listing, context.preferences)

    with pytest.raises(MatchingPersistenceError, match="inconsistent matching counts"):
        repository.persist_page(
            context,
            (EvaluatedCandidate(candidate=candidate, result=result),),
        )


def test_persistence_rejects_candidate_substitution() -> None:
    client = FakeClient({"get_matching_context_page": context_response(job_row())})
    repository = MatchingRepository(client)
    context = repository.load_page(USER_ID)
    candidate = context.candidates[0]
    substituted = replace(candidate, job_id=SECOND_JOB_ID)
    result = JobMatcher().evaluate(candidate.listing, context.preferences)

    with pytest.raises(ValueError, match="every matching candidate"):
        repository.persist_page(
            context,
            (EvaluatedCandidate(candidate=substituted, result=result),),
        )


def test_runner_finalizes_without_writing_when_every_match_is_current() -> None:
    client = FakeClient(
        {
            "get_matching_context_page": context_response(),
            "finalize_job_match_results": {"removed": 2},
        }
    )

    stats = MatchingRunner(MatchingRepository(client)).run(USER_ID)

    assert stats.evaluated == 0
    assert [call[0] for call in client.calls] == [
        "get_matching_context_page",
        "finalize_job_match_results",
    ]
