"""Greenhouse public Job Board API adapter."""

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from launchpad_worker.models import JobListing, SourceFetchResult, SourceItemIssue
from launchpad_worker.normalize import (
    canonicalize_apply_url,
    html_to_text,
    normalize_optional_text,
)
from launchpad_worker.sources.base import JobSource, SourceFetchError

BOARD_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class _GreenhouseLocation(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None


class _GreenhouseNamedItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str


class _GreenhouseJob(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    title: str
    updated_at: datetime | None = None
    location: _GreenhouseLocation | None = None
    absolute_url: str
    content: str | None = None
    departments: list[_GreenhouseNamedItem] = Field(default_factory=list)
    offices: list[_GreenhouseNamedItem] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("job title must not be blank")
        return normalized


class _GreenhouseResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    jobs: list[Any]


class GreenhouseJobSource(JobSource):
    """Fetch public job posts for one Greenhouse board token."""

    source_type = "greenhouse"
    base_url: ClassVar[str] = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(
        self,
        board_token: str,
        *,
        http_client: httpx.Client | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not BOARD_TOKEN_PATTERN.fullmatch(board_token):
            raise ValueError("Greenhouse board token contains unsupported characters")
        self.board_token = board_token
        self._http_client = http_client
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def jobs_url(self) -> str:
        """Return the documented public list-jobs endpoint."""
        return f"{self.base_url}/{self.board_token}/jobs"

    def fetch_jobs(self) -> SourceFetchResult:
        """Fetch and normalize all valid jobs in one Greenhouse response."""
        if self._http_client is not None:
            return self._fetch_with_client(self._http_client)

        timeout = httpx.Timeout(10.0, connect=5.0)
        headers = {"Accept": "application/json", "User-Agent": "Launchpad/0.1"}
        with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
            return self._fetch_with_client(client)

    def _fetch_with_client(self, client: httpx.Client) -> SourceFetchResult:
        try:
            response = client.get(self.jobs_url, params={"content": "true"})
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SourceFetchError(
                source_type=self.source_type,
                error_code="request_failed",
                message=f"Greenhouse request failed: {type(error).__name__}",
            ) from error

        try:
            payload = _GreenhouseResponse.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise SourceFetchError(
                source_type=self.source_type,
                error_code="invalid_response",
                message="Greenhouse returned an invalid list-jobs response",
            ) from error

        jobs: list[JobListing] = []
        issues: list[SourceItemIssue] = []
        for index, raw_job in enumerate(payload.jobs):
            try:
                job = _GreenhouseJob.model_validate(raw_job)
                jobs.append(self._normalize_job(job))
            except (ValueError, ValidationError) as error:
                issues.append(
                    SourceItemIssue(
                        item_index=index,
                        external_id=self._read_external_id(raw_job),
                        error_code="invalid_job",
                        message=self._safe_validation_message(error),
                    )
                )

        return SourceFetchResult(
            jobs=tuple(jobs),
            issues=tuple(issues),
            fetched_at=self._clock(),
        )

    def _normalize_job(self, job: _GreenhouseJob) -> JobListing:
        external_id = str(job.id)
        location_name = job.location.name if job.location else None
        return JobListing(
            external_id=external_id,
            dedupe_key=f"external:{external_id}",
            title=job.title,
            location=normalize_optional_text(location_name),
            apply_url=job.absolute_url.strip(),
            canonical_apply_url=canonicalize_apply_url(job.absolute_url),
            # The list-jobs endpoint documents updated_at but not first_published.
            # Treating updated_at as a posting date would violate Launchpad's timestamp contract.
            employer_posted_at=None,
            source_updated_at=job.updated_at,
            description=html_to_text(job.content),
            department_names=self._unique_names(job.departments),
            office_names=self._unique_names(job.offices),
        )

    @staticmethod
    def _unique_names(items: list[_GreenhouseNamedItem]) -> tuple[str, ...]:
        names = {
            normalized
            for item in items
            if (normalized := normalize_optional_text(item.name)) is not None
        }
        return tuple(sorted(names, key=str.casefold))

    @staticmethod
    def _read_external_id(raw_job: Any) -> str | None:
        if not isinstance(raw_job, Mapping):
            return None
        value = raw_job.get("id")
        return str(value) if isinstance(value, (str, int)) else None

    @staticmethod
    def _safe_validation_message(error: ValueError | ValidationError) -> str:
        if isinstance(error, ValidationError):
            first_error = error.errors(include_url=False, include_input=False)[0]
            field = ".".join(str(part) for part in first_error["loc"])
            return f"Invalid {field}: {first_error['msg']}"
        return str(error)
