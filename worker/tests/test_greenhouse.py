"""Deterministic tests for the Greenhouse Job Board adapter."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from launchpad_worker.sources import GreenhouseJobSource, SourceFetchError

FIXTURES = Path(__file__).parent / "fixtures"
FETCHED_AT = datetime(2026, 10, 30, 18, 30, tzinfo=UTC)


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_source(
    handler: httpx.MockTransport,
    *,
    board_token: str = "launchpad-fixture",
) -> GreenhouseJobSource:
    client = httpx.Client(transport=handler)
    return GreenhouseJobSource(board_token, http_client=client, clock=lambda: FETCHED_AT)


@pytest.mark.unit
def test_fetches_documented_endpoint_and_normalizes_fixture() -> None:
    payload = load_fixture("greenhouse_jobs.json")

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/boards/launchpad-fixture/jobs"
        assert request.url.params.get("content") == "true"
        assert len(request.url.params) == 1
        return httpx.Response(200, json=payload)

    result = make_source(httpx.MockTransport(handle)).fetch_jobs()

    assert result.fetched_at == FETCHED_AT
    assert result.is_partial is False
    assert len(result.jobs) == 2
    first = result.jobs[0]
    assert first.external_id == "127817"
    assert first.dedupe_key == "external:127817"
    assert first.title == "Software Engineer, New Grad"
    assert first.location == "San Francisco, CA"
    assert first.description == "Build dependable systems for new graduates."
    assert first.department_names == ("Engineering",)
    assert first.office_names == ("San Francisco", "West Coast")


@pytest.mark.unit
def test_preserves_timestamp_semantics_and_job_identity_query() -> None:
    payload = load_fixture("greenhouse_jobs.json")
    source = make_source(httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))

    first = source.fetch_jobs().jobs[0]

    assert first.employer_posted_at is None
    assert first.source_updated_at == datetime(2026, 10, 29, 23, 45, 12, tzinfo=UTC)
    assert first.apply_url.endswith("utm_source=fixture#apply")
    assert first.canonical_apply_url == "https://careers.example.test/jobs?gh_jid=127817"


@pytest.mark.unit
def test_skips_malformed_item_and_marks_result_partial() -> None:
    payload = load_fixture("greenhouse_jobs.json")
    payload["jobs"].append(
        {
            "id": 127819,
            "title": "   ",
            "updated_at": "not-a-date",
            "absolute_url": "not-a-url",
        }
    )
    payload["jobs"].append(None)
    source = make_source(httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))

    result = source.fetch_jobs()

    assert len(result.jobs) == 2
    assert result.is_partial is True
    assert len(result.issues) == 2
    assert result.issues[0].item_index == 2
    assert result.issues[0].external_id == "127819"
    assert result.issues[0].error_code == "invalid_job"
    assert result.issues[1].item_index == 3
    assert result.issues[1].external_id is None


@pytest.mark.unit
def test_successful_empty_response_is_not_a_failure() -> None:
    source = make_source(
        httpx.MockTransport(lambda _: httpx.Response(200, json={"jobs": [], "meta": {"total": 0}}))
    )

    result = source.fetch_jobs()

    assert result.jobs == ()
    assert result.issues == ()
    assert result.is_partial is False


@pytest.mark.unit
def test_http_failure_raises_sanitized_source_error() -> None:
    source = make_source(
        httpx.MockTransport(
            lambda _: httpx.Response(503, text="private upstream response that must not be logged")
        )
    )

    with pytest.raises(SourceFetchError) as raised:
        source.fetch_jobs()

    assert raised.value.error_code == "request_failed"
    assert raised.value.source_type == "greenhouse"
    assert "private upstream" not in str(raised.value)


@pytest.mark.unit
def test_invalid_top_level_payload_raises_source_error() -> None:
    source = make_source(httpx.MockTransport(lambda _: httpx.Response(200, json={"items": []})))

    with pytest.raises(SourceFetchError, match="invalid list-jobs response") as raised:
        source.fetch_jobs()

    assert raised.value.error_code == "invalid_response"


@pytest.mark.unit
@pytest.mark.parametrize("board_token", ["", "../private", "board/token", "board token"])
def test_rejects_unsafe_board_tokens(board_token: str) -> None:
    with pytest.raises(ValueError, match="board token"):
        GreenhouseJobSource(board_token)
