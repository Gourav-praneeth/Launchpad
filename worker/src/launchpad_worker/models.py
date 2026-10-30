"""Source-agnostic discovery models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class JobListing:
    """A normalized job post emitted by any source adapter."""

    external_id: str | None
    dedupe_key: str
    title: str
    location: str | None
    apply_url: str
    canonical_apply_url: str
    employer_posted_at: datetime | None
    source_updated_at: datetime | None
    description: str | None
    department_names: tuple[str, ...] = ()
    office_names: tuple[str, ...] = ()
    employment_type: str | None = None
    workplace_type: str | None = None


@dataclass(frozen=True, slots=True)
class SourceItemIssue:
    """A malformed source item skipped without discarding valid siblings."""

    item_index: int
    external_id: str | None
    error_code: str
    message: str


@dataclass(frozen=True, slots=True)
class SourceFetchResult:
    """The complete outcome of one successful source response."""

    jobs: tuple[JobListing, ...]
    issues: tuple[SourceItemIssue, ...]
    fetched_at: datetime

    @property
    def is_partial(self) -> bool:
        """Return whether at least one source item was rejected."""
        return bool(self.issues)
