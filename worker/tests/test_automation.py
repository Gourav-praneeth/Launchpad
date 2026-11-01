"""Tests for fault-isolated scheduled orchestration."""

from dataclasses import dataclass
from typing import Any

from launchpad_worker.automation import (
    AutomationRepository,
    AutomationRunner,
    AutomationTargets,
)
from launchpad_worker.notifications import DispatchStats, QueuedNotifications
from launchpad_worker.sources import SourceFetchError

SOURCE_ONE = "30000000-0000-0000-0000-000000000001"
SOURCE_TWO = "30000000-0000-0000-0000-000000000002"
USER_ONE = "10000000-0000-0000-0000-000000000001"
USER_TWO = "10000000-0000-0000-0000-000000000002"


@dataclass
class FakeResponse:
    data: Any


class FakeRequest:
    def __init__(self, data: Any) -> None:
        self.data = data

    def execute(self) -> FakeResponse:
        return FakeResponse(self.data)


class FakeClient:
    def __init__(self, data: Any) -> None:
        self.data = data

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRequest:
        return FakeRequest(self.data)


def test_repository_parses_unique_automation_targets() -> None:
    targets = AutomationRepository(
        FakeClient(
            {
                "source_ids": [SOURCE_ONE, SOURCE_TWO],
                "user_ids": [USER_ONE],
            }
        )
    ).load()

    assert targets.source_ids == (SOURCE_ONE, SOURCE_TWO)
    assert targets.user_ids == (USER_ONE,)


class FakeTargets:
    def load(self) -> AutomationTargets:
        return AutomationTargets(
            source_ids=(SOURCE_ONE, SOURCE_TWO),
            user_ids=(USER_ONE, USER_TWO),
        )


class FakeSources:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, source_id: str) -> None:
        self.calls.append(source_id)
        if source_id == SOURCE_ONE:
            raise SourceFetchError(
                source_type="fixture",
                error_code="request_failed",
                message="Fixture timeout",
            )


class FakeMatching:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, user_id: str) -> None:
        self.calls.append(user_id)


class FakeNotifications:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def queue_for_user(self, user_id: str) -> QueuedNotifications:
        self.calls.append(user_id)
        return QueuedNotifications(queued=1)


class FakeDispatcher:
    def drain(self, *, maximum_deliveries: int) -> DispatchStats:
        return DispatchStats(
            claimed=1,
            sent=1,
            retry_scheduled=0,
            permanently_failed=0,
        )


def test_cycle_continues_after_one_source_failure() -> None:
    sources = FakeSources()
    matching = FakeMatching()
    notifications = FakeNotifications()
    runner = AutomationRunner(
        FakeTargets(),
        sources,
        matching,
        notifications,
        dispatcher=FakeDispatcher(),  # type: ignore[arg-type]
    )

    stats = runner.run(maximum_deliveries=10)

    assert sources.calls == [SOURCE_ONE, SOURCE_TWO]
    assert matching.calls == [USER_ONE, USER_TWO]
    assert notifications.calls == [USER_ONE, USER_TWO]
    assert stats.sources_succeeded == 1
    assert stats.sources_failed == 1
    assert stats.users_succeeded == 2
    assert stats.notifications_queued == 2
    assert stats.delivery is not None and stats.delivery.sent == 1
    assert stats.has_failures is True


def test_cycle_can_queue_without_email_delivery() -> None:
    stats = AutomationRunner(
        FakeTargets(),
        FakeSources(),
        FakeMatching(),
        FakeNotifications(),
    ).run()

    assert stats.delivery is None
