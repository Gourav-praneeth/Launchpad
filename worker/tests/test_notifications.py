"""Tests for durable notification persistence and provider-safe email delivery."""

from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from launchpad_worker.notifications import (
    DeliveryCompletion,
    DigestJob,
    EmailDeliveryError,
    NotificationDelivery,
    NotificationDispatcher,
    NotificationPersistenceError,
    NotificationRepository,
    ResendEmailProvider,
    render_digest,
)

USER_ID = "10000000-0000-0000-0000-000000000001"
DELIVERY_ID = "60000000-0000-0000-0000-000000000001"
JOB_ID = "40000000-0000-0000-0000-000000000001"


@dataclass
class FakeResponse:
    data: Any


class FakeRequest:
    def __init__(self, data: Any) -> None:
        self._data = data

    def execute(self) -> FakeResponse:
        if isinstance(self._data, Exception):
            raise self._data
        return FakeResponse(self._data)


class FakeClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRequest:
        self.calls.append((name, params))
        response = self.responses[name]
        if isinstance(response, list):
            response = response.pop(0)
        return FakeRequest(response)


def delivery_payload() -> dict[str, Any]:
    return {
        "id": DELIVERY_ID,
        "dedupe_key": "job-digest/fixture",
        "recipient_email": "graduate@launchpad.test",
        "subject": "A fresh Launchpad job match",
        "attempt_count": 1,
        "payload": [
            {
                "job_id": JOB_ID,
                "title": "Software Engineer, New Grad",
                "company": "Fixture Systems",
                "location": "Remote",
                "workplace_type": "remote",
                "employment_type": "full-time",
                "apply_url": "https://careers.example.test/jobs/1",
                "first_seen_at": "2026-11-01T10:00:00Z",
            }
        ],
    }


def parsed_delivery(*, title: str = "Software Engineer, New Grad") -> NotificationDelivery:
    return NotificationDelivery(
        id=DELIVERY_ID,
        dedupe_key="job-digest/fixture",
        recipient_email="graduate@launchpad.test",
        subject="A fresh Launchpad job match",
        jobs=(
            DigestJob(
                job_id=JOB_ID,
                title=title,
                company="Fixture Systems",
                location="Remote",
                workplace_type="remote",
                employment_type="full-time",
                apply_url="https://careers.example.test/jobs/1",
                first_seen_at="2026-11-01T10:00:00Z",
            ),
        ),
        attempt_count=1,
    )


def test_repository_queues_claims_and_completes_through_rpc() -> None:
    client = FakeClient(
        {
            "queue_match_notifications": {"queued": 2},
            "claim_notification_delivery": delivery_payload(),
            "complete_notification_delivery": {
                "status": "sent",
                "next_attempt_at": None,
            },
        }
    )
    repository = NotificationRepository(client)

    assert repository.queue_for_user(USER_ID).queued == 2
    delivery = repository.claim(maximum_items=25, lease_minutes=10)
    assert delivery is not None
    assert delivery.jobs[0].title == "Software Engineer, New Grad"
    completion = repository.complete(
        delivery.id,
        delivered=True,
        provider_id="provider-123",
    )

    assert completion.status == "sent"
    assert [name for name, _ in client.calls] == [
        "queue_match_notifications",
        "claim_notification_delivery",
        "complete_notification_delivery",
    ]
    assert client.calls[2][1]["provider_id"] == "provider-123"


def test_repository_returns_none_for_an_empty_due_queue() -> None:
    repository = NotificationRepository(FakeClient({"claim_notification_delivery": None}))

    assert repository.claim() is None


def test_repository_rejects_malformed_or_unsafe_delivery_payload() -> None:
    payload = delivery_payload()
    payload["payload"][0]["apply_url"] = "javascript:alert(1)"
    repository = NotificationRepository(FakeClient({"claim_notification_delivery": payload}))

    with pytest.raises(NotificationPersistenceError, match="apply_url"):
        repository.claim()


def test_digest_renderer_escapes_listing_text_and_keeps_official_link() -> None:
    message = render_digest(
        parsed_delivery(title="<script>bad()</script>"),
        from_address="Launchpad <alerts@launchpad.test>",
        app_base_url="https://launchpad.example.test/",
    )

    assert "<script>" not in message.html
    assert "&lt;script&gt;" in message.html
    assert "https://careers.example.test/jobs/1" in message.html
    assert message.idempotency_key == "job-digest/fixture"
    assert "Freshness is based on Launchpad discovery time" in message.text


def test_resend_provider_sends_idempotency_header_and_expected_payload() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["header"] = request.headers["Idempotency-Key"]
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"id": "resend-123"})

    provider = ResendEmailProvider(
        "re_test_key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    message = render_digest(
        parsed_delivery(),
        from_address="Launchpad <alerts@launchpad.test>",
        app_base_url="https://launchpad.example.test",
    )

    assert provider.send(message) == "resend-123"
    assert captured["header"] == "job-digest/fixture"
    assert captured["authorization"] == "Bearer re_test_key"
    assert "graduate@launchpad.test" in captured["body"]


def test_resend_provider_wraps_http_errors_without_response_body() -> None:
    provider = ResendEmailProvider(
        "re_test_key",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(429, text="sensitive provider response")
            )
        ),
    )
    message = render_digest(
        parsed_delivery(),
        from_address="Launchpad <alerts@launchpad.test>",
        app_base_url="https://launchpad.example.test",
    )

    with pytest.raises(EmailDeliveryError, match="HTTP 429") as raised:
        provider.send(message)

    assert "sensitive" not in str(raised.value)


class FakeRepository:
    def __init__(self, deliveries: list[NotificationDelivery | None]) -> None:
        self.deliveries = deliveries
        self.completions: list[dict[str, Any]] = []

    def claim(self) -> NotificationDelivery | None:
        return self.deliveries.pop(0)

    def complete(self, delivery_id: str, **kwargs: Any) -> DeliveryCompletion:
        self.completions.append({"delivery_id": delivery_id, **kwargs})
        if kwargs["delivered"]:
            return DeliveryCompletion(status="sent", next_attempt_at=None)
        return DeliveryCompletion(
            status="pending",
            next_attempt_at="2026-11-01T10:05:00Z",
        )


class SuccessfulProvider:
    def send(self, message: Any) -> str:
        return "provider-123"


class FailingProvider:
    def send(self, message: Any) -> str:
        raise EmailDeliveryError("Provider unavailable")


def test_dispatcher_completes_successful_delivery() -> None:
    repository = FakeRepository([parsed_delivery(), None])
    dispatcher = NotificationDispatcher(
        repository,  # type: ignore[arg-type]
        SuccessfulProvider(),
        from_address="Launchpad <alerts@launchpad.test>",
        app_base_url="https://launchpad.example.test",
    )

    stats = dispatcher.drain()

    assert stats.sent == 1
    assert repository.completions[0]["delivered"] is True
    assert repository.completions[0]["provider_id"] == "provider-123"


def test_dispatcher_records_retryable_provider_failure() -> None:
    repository = FakeRepository([parsed_delivery(), None])
    dispatcher = NotificationDispatcher(
        repository,  # type: ignore[arg-type]
        FailingProvider(),
        from_address="Launchpad <alerts@launchpad.test>",
        app_base_url="https://launchpad.example.test",
    )

    stats = dispatcher.drain()

    assert stats.retry_scheduled == 1
    assert repository.completions[0]["delivered"] is False
    assert repository.completions[0]["error_summary"] == "Provider unavailable"
