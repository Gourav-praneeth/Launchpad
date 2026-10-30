from dataclasses import replace
from datetime import UTC, datetime

import pytest

from launchpad_worker.matching import (
    CareerLevel,
    JobMatcher,
    JobPreferences,
    MatchStatus,
    SponsorshipPreference,
    SponsorshipStatus,
    canonical_employment_type,
    canonical_workplace_type,
    classify_career_level,
    classify_sponsorship,
)
from launchpad_worker.models import JobListing

pytestmark = pytest.mark.unit


def make_job(**overrides: object) -> JobListing:
    values: dict[str, object] = {
        "external_id": "job-123",
        "dedupe_key": "greenhouse:job-123",
        "title": "Software Engineer, New Grad",
        "location": "San Francisco, CA",
        "apply_url": "https://example.com/jobs/123",
        "canonical_apply_url": "https://example.com/jobs/123",
        "employer_posted_at": datetime(2026, 10, 20, tzinfo=UTC),
        "source_updated_at": datetime(2026, 10, 21, tzinfo=UTC),
        "description": "Build backend services. Visa sponsorship is available.",
        "employment_type": "Full Time",
        "workplace_type": "Hybrid",
    }
    values.update(overrides)
    return JobListing(**values)  # type: ignore[arg-type]


def reason_codes(result: object, attribute: str) -> set[str]:
    return {reason.code for reason in getattr(result, attribute)}


def test_matching_job_returns_explainable_match() -> None:
    preferences = JobPreferences(
        locations=("San Francisco",),
        workplace_types=("hybrid",),
        include_keywords=("backend", "distributed systems"),
        sponsorship_preference=SponsorshipPreference.REQUIRED,
    )

    result = JobMatcher().evaluate(make_job(), preferences)

    assert result.status is MatchStatus.MATCHED
    assert result.career_level is CareerLevel.NEW_GRAD
    assert result.sponsorship_status is SponsorshipStatus.AVAILABLE
    assert reason_codes(result, "match_reasons") == {
        "title_match",
        "career_level_match",
        "employment_type_match",
        "workplace_type_match",
        "location_match",
        "included_keyword",
        "sponsorship_available",
    }
    assert result.review_reasons == ()
    assert result.rejection_reasons == ()


def test_senior_role_is_rejected_by_default() -> None:
    result = JobMatcher().evaluate(
        make_job(title="Senior Software Engineer"),
        JobPreferences(),
    )

    assert result.status is MatchStatus.REJECTED
    assert "senior_role_excluded" in reason_codes(result, "rejection_reasons")


def test_senior_role_can_be_explicitly_enabled() -> None:
    preferences = JobPreferences(
        career_levels=(CareerLevel.EXPERIENCED,),
        include_senior_roles=True,
    )

    result = JobMatcher().evaluate(
        make_job(title="Senior Software Engineer"),
        preferences,
    )

    assert result.status is MatchStatus.MATCHED
    assert result.career_level is CareerLevel.EXPERIENCED


def test_unknown_career_level_requires_review() -> None:
    result = JobMatcher().evaluate(
        make_job(title="Software Engineer"),
        JobPreferences(),
    )

    assert result.status is MatchStatus.REVIEW
    assert "career_level_unknown" in reason_codes(result, "review_reasons")


def test_configured_metadata_that_is_unknown_requires_review() -> None:
    preferences = JobPreferences(
        locations=("Seattle",),
        workplace_types=("remote",),
    )

    result = JobMatcher().evaluate(
        make_job(location=None, employment_type=None, workplace_type=None),
        preferences,
    )

    assert result.status is MatchStatus.REVIEW
    assert reason_codes(result, "review_reasons") == {
        "employment_type_unknown",
        "workplace_type_unknown",
        "location_unknown",
    }


def test_clear_location_mismatch_is_rejected() -> None:
    preferences = JobPreferences(locations=("New York",))

    result = JobMatcher().evaluate(make_job(), preferences)

    assert result.status is MatchStatus.REJECTED
    assert "location_mismatch" in reason_codes(result, "rejection_reasons")


def test_internship_is_rejected_when_full_time_is_requested() -> None:
    result = JobMatcher().evaluate(
        make_job(employment_type="Internship"),
        JobPreferences(),
    )

    assert result.status is MatchStatus.REJECTED
    assert "employment_type_mismatch" in reason_codes(result, "rejection_reasons")


def test_excluded_keyword_overrides_other_matches() -> None:
    preferences = JobPreferences(exclude_keywords=("backend",))

    result = JobMatcher().evaluate(make_job(), preferences)

    assert result.status is MatchStatus.REJECTED
    assert "excluded_keyword" in reason_codes(result, "rejection_reasons")


def test_include_keywords_use_any_match_semantics() -> None:
    matcher = JobMatcher()
    matching = matcher.evaluate(
        make_job(),
        JobPreferences(include_keywords=("backend", "machine learning")),
    )
    missing = matcher.evaluate(
        make_job(),
        JobPreferences(include_keywords=("ios", "machine learning")),
    )

    assert matching.status is MatchStatus.MATCHED
    assert missing.status is MatchStatus.REJECTED
    assert "required_keyword_missing" in reason_codes(missing, "rejection_reasons")


@pytest.mark.parametrize(
    ("description", "expected_status", "expected_reason"),
    [
        (
            "We cannot sponsor employment visas.",
            MatchStatus.REJECTED,
            "sponsorship_unavailable",
        ),
        (None, MatchStatus.REVIEW, "sponsorship_unknown"),
        (
            "Visa sponsorship is available.",
            MatchStatus.MATCHED,
            "sponsorship_available",
        ),
    ],
)
def test_required_sponsorship_uses_explicit_evidence(
    description: str | None,
    expected_status: MatchStatus,
    expected_reason: str,
) -> None:
    result = JobMatcher().evaluate(
        make_job(description=description),
        JobPreferences(sponsorship_preference=SponsorshipPreference.REQUIRED),
    )

    assert result.status is expected_status
    all_codes = (
        reason_codes(result, "match_reasons")
        | reason_codes(result, "review_reasons")
        | reason_codes(result, "rejection_reasons")
    )
    assert expected_reason in all_codes


def test_freshness_timestamps_do_not_change_matching() -> None:
    original = make_job()
    newer = replace(
        original,
        employer_posted_at=datetime(2026, 10, 30, tzinfo=UTC),
        source_updated_at=datetime(2026, 10, 30, tzinfo=UTC),
    )

    assert JobMatcher().evaluate(original, JobPreferences()) == JobMatcher().evaluate(
        newer, JobPreferences()
    )


def test_matching_is_deterministic() -> None:
    matcher = JobMatcher()
    listing = make_job()
    preferences = JobPreferences(locations=("San Francisco",))

    assert matcher.evaluate(listing, preferences) == matcher.evaluate(listing, preferences)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Software Engineer, University Graduate", CareerLevel.NEW_GRAD),
        ("Junior Backend Engineer", CareerLevel.ENTRY_LEVEL),
        ("Software Engineer - Early Career", CareerLevel.EARLY_CAREER),
        ("Principal Software Engineer", CareerLevel.EXPERIENCED),
        ("Software Engineer", CareerLevel.UNKNOWN),
    ],
)
def test_career_level_classification(title: str, expected: CareerLevel) -> None:
    assert classify_career_level(title) is expected


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("We will not sponsor applicants.", SponsorshipStatus.UNAVAILABLE),
        ("We can sponsor qualified candidates.", SponsorshipStatus.AVAILABLE),
        ("Work authorization required.", SponsorshipStatus.UNKNOWN),
    ],
)
def test_sponsorship_classification(
    description: str,
    expected: SponsorshipStatus,
) -> None:
    assert classify_sponsorship(description) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Full Time", "full-time"),
        ("intern", "internship"),
        ("freelance", None),
    ],
)
def test_employment_type_canonicalization(value: str, expected: str | None) -> None:
    assert canonical_employment_type(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Remote", "remote"),
        ("In Office", "on-site"),
        ("flexible", None),
    ],
)
def test_workplace_type_canonicalization(value: str, expected: str | None) -> None:
    assert canonical_workplace_type(value) == expected


def test_unknown_career_level_cannot_be_configured_as_eligible() -> None:
    with pytest.raises(ValueError, match="unknown cannot be an eligible career level"):
        JobPreferences(career_levels=(CareerLevel.UNKNOWN,))
