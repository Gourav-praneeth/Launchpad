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


def test_match_command_accepts_only_a_user_uuid() -> None:
    arguments = build_parser().parse_args(["match", "--user-id", SOURCE_ID])

    assert arguments.command == "match"
    assert arguments.user_id == UUID(SOURCE_ID)


def test_match_command_rejects_invalid_user_id() -> None:
    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(["match", "--user-id", "not-a-uuid"])

    assert raised.value.code == 2


def test_cycle_command_supports_queue_only_local_verification() -> None:
    arguments = build_parser().parse_args(["cycle", "--skip-email", "--max-deliveries", "25"])

    assert arguments.command == "cycle"
    assert arguments.skip_email is True
    assert arguments.max_deliveries == 25


def test_deliver_command_has_a_bounded_default() -> None:
    arguments = build_parser().parse_args(["deliver"])

    assert arguments.command == "deliver"
    assert arguments.max_deliveries == 100
