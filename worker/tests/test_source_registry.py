"""Tests for database-backed source configuration."""

from dataclasses import dataclass
from typing import Any, Self

import pytest

from launchpad_worker.source_registry import (
    ConfiguredSource,
    SourceRegistry,
    SourceRegistryError,
    build_job_source,
)
from launchpad_worker.sources import GreenhouseJobSource

SOURCE_ID = "30000000-0000-0000-0000-000000000001"


@dataclass
class FakeResponse:
    data: Any


class FakeQuery:
    def __init__(self, data: Any) -> None:
        self.data = data
        self.selected: str | None = None
        self.filters: list[tuple[str, Any]] = []
        self.limit_count: int | None = None

    def select(self, columns: str) -> Self:
        self.selected = columns
        return self

    def eq(self, column: str, value: Any) -> Self:
        self.filters.append((column, value))
        return self

    def limit(self, count: int) -> Self:
        self.limit_count = count
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse(self.data)


class FakeClient:
    def __init__(self, data: Any) -> None:
        self.query = FakeQuery(data)
        self.table_name: str | None = None

    def table(self, table_name: str) -> FakeQuery:
        self.table_name = table_name
        return self.query


def configured_source(**overrides: object) -> ConfiguredSource:
    values: dict[str, object] = {
        "id": SOURCE_ID,
        "source_type": "greenhouse",
        "source_url": ("https://boards-api.greenhouse.io/v1/boards/launchpad-fixture/jobs"),
        "is_active": True,
    }
    values.update(overrides)
    return ConfiguredSource(**values)  # type: ignore[arg-type]


def test_registry_loads_one_source_by_id() -> None:
    row = {
        "id": SOURCE_ID,
        "source_type": "greenhouse",
        "source_url": "https://boards-api.greenhouse.io/v1/boards/launchpad-fixture/jobs",
        "is_active": True,
    }
    client = FakeClient([row])

    source = SourceRegistry(client).get(SOURCE_ID)

    assert source == configured_source()
    assert client.table_name == "sources"
    assert client.query.selected == "id,source_type,source_url,is_active"
    assert client.query.filters == [("id", SOURCE_ID)]
    assert client.query.limit_count == 2


@pytest.mark.parametrize("data", [[], [{"id": SOURCE_ID}, {"id": "another"}], None])
def test_registry_rejects_missing_or_ambiguous_results(data: Any) -> None:
    with pytest.raises(SourceRegistryError, match="not found"):
        SourceRegistry(FakeClient(data)).get(SOURCE_ID)


def test_builds_greenhouse_adapter_from_official_api_url() -> None:
    source = build_job_source(configured_source())

    assert isinstance(source, GreenhouseJobSource)
    assert source.board_token == "launchpad-fixture"


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (configured_source(is_active=False), "inactive"),
        (configured_source(source_type="lever"), "Unsupported source type"),
        (
            configured_source(source_url="https://boards.greenhouse.io/launchpad-fixture"),
            "official list-jobs endpoint",
        ),
        (
            configured_source(
                source_url=(
                    "https://boards-api.greenhouse.io/v1/boards/launchpad-fixture/jobs"
                    "?tracking=true"
                )
            ),
            "official list-jobs endpoint",
        ),
    ],
)
def test_rejects_inactive_unsupported_or_unsafe_sources(
    source: ConfiguredSource,
    message: str,
) -> None:
    with pytest.raises(SourceRegistryError, match=message):
        build_job_source(source)
