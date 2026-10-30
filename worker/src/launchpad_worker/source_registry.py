"""Database-backed configuration for monitored job sources."""

import re
from dataclasses import dataclass
from typing import Any, Protocol, Self

from launchpad_worker.sources import GreenhouseJobSource, JobSource

GREENHOUSE_API_URL = re.compile(
    r"^https://boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)/jobs/?$"
)


class _TableResponse(Protocol):
    data: Any


class _TableQuery(Protocol):
    def select(self, columns: str) -> Self: ...

    def eq(self, column: str, value: Any) -> Self: ...

    def limit(self, count: int) -> Self: ...

    def execute(self) -> _TableResponse: ...


class TableClient(Protocol):
    def table(self, table_name: str) -> _TableQuery: ...


class SourceRegistryError(RuntimeError):
    """A monitored source is missing, unsafe, or unsupported."""


@dataclass(frozen=True, slots=True)
class ConfiguredSource:
    """The database fields needed to construct one source adapter."""

    id: str
    source_type: str
    source_url: str
    is_active: bool


class SourceRegistry:
    """Load monitored source configuration through the trusted database client."""

    def __init__(self, client: TableClient) -> None:
        self._client = client

    def get(self, source_id: str) -> ConfiguredSource:
        """Return one source or raise a safe configuration error."""
        try:
            response = (
                self._client.table("sources")
                .select("id,source_type,source_url,is_active")
                .eq("id", source_id)
                .limit(2)
                .execute()
            )
        except Exception as error:
            raise SourceRegistryError("Unable to load source configuration") from error

        if not isinstance(response.data, list) or len(response.data) != 1:
            raise SourceRegistryError("Source configuration was not found")
        row = response.data[0]
        if not isinstance(row, dict):
            raise SourceRegistryError("Source configuration is invalid")

        configured = ConfiguredSource(
            id=self._required_string(row, "id"),
            source_type=self._required_string(row, "source_type"),
            source_url=self._required_string(row, "source_url"),
            is_active=self._required_boolean(row, "is_active"),
        )
        if configured.id != source_id:
            raise SourceRegistryError("Database returned the wrong source configuration")
        return configured

    @staticmethod
    def _required_string(row: dict[str, Any], key: str) -> str:
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SourceRegistryError(f"Source configuration has an invalid {key}")
        return value.strip()

    @staticmethod
    def _required_boolean(row: dict[str, Any], key: str) -> bool:
        value = row.get(key)
        if not isinstance(value, bool):
            raise SourceRegistryError(f"Source configuration has an invalid {key}")
        return value


def build_job_source(configured: ConfiguredSource) -> JobSource:
    """Construct the independent adapter selected by a database source row."""
    if not configured.is_active:
        raise SourceRegistryError("Source configuration is inactive")
    if configured.source_type != "greenhouse":
        raise SourceRegistryError(f"Unsupported source type: {configured.source_type}")

    match = GREENHOUSE_API_URL.fullmatch(configured.source_url)
    if match is None:
        raise SourceRegistryError("Greenhouse source URL is not an official list-jobs endpoint")
    return GreenhouseJobSource(match.group(1))
