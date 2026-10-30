"""Tests for the operational worker command interface."""

from uuid import UUID

import pytest

from launchpad_worker.cli import build_parser

SOURCE_ID = "30000000-0000-0000-0000-000000000001"


def test_discover_command_accepts_only_a_source_uuid() -> None:
    arguments = build_parser().parse_args(["discover", "--source-id", SOURCE_ID])

    assert arguments.command == "discover"
    assert arguments.source_id == UUID(SOURCE_ID)


def test_discover_command_rejects_invalid_source_id() -> None:
    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(["discover", "--source-id", "not-a-uuid"])

    assert raised.value.code == 2
