"""Durable notification queueing, digest rendering, and idempotent email delivery."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import UUID

import httpx

from launchpad_worker.persistence import DatabaseClient


class NotificationPersistenceError(RuntimeError):
    """Notification queue state could not be loaded or committed safely."""


class EmailDeliveryError(RuntimeError):
    """An email provider rejected or could not complete a request."""


@dataclass(frozen=True, slots=True)
class QueuedNotifications:
    """Count of newly inserted per-job notification items."""

    queued: int


@dataclass(frozen=True, slots=True)
class DigestJob:
    """Immutable job snapshot included in one email delivery."""

    job_id: str
    title: str
    company: str
    location: str | None
    workplace_type: str | None
    employment_type: str | None
    apply_url: str
    first_seen_at: str


@dataclass(frozen=True, slots=True)
class NotificationDelivery:
    """One leased immutable email digest."""

    id: str
    dedupe_key: str
    recipient_email: str
    subject: str
    jobs: tuple[DigestJob, ...]
    attempt_count: int


@dataclass(frozen=True, slots=True)
class DeliveryCompletion:
    """Database state after recording one provider outcome."""

    status: str
    next_attempt_at: str | None


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """Provider-neutral email content."""

    from_address: str
    to_address: str
    subject: str
    html: str
    text: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class DispatchStats:
    """Email delivery outcomes for one worker invocation."""

    claimed: int
    sent: int
    retry_scheduled: int
    permanently_failed: int


class EmailProvider(Protocol):
    """Send one immutable email request and return the provider message ID."""

    def send(self, message: EmailMessage) -> str: ...


class NotificationRepository:
    """Access service-role-only notification queue functions."""

    def __init__(self, client: DatabaseClient) -> None:
        self._client = client

    def queue_for_user(self, user_id: str) -> QueuedNotifications:
        """Create missing per-job notification items for current matches."""
        normalized_user_id = self._uuid(user_id, "user_id")
        data = self._call("queue_match_notifications", {"target_user_id": normalized_user_id})
        return QueuedNotifications(queued=self._count(data, "queued"))

    def claim(
        self, *, maximum_items: int = 50, lease_minutes: int = 15
    ) -> NotificationDelivery | None:
        """Lease an existing retry or atomically create and lease a new digest."""
        if not 1 <= maximum_items <= 100:
            raise ValueError("maximum_items must be between 1 and 100")
        if not 1 <= lease_minutes <= 60:
            raise ValueError("lease_minutes must be between 1 and 60")
        try:
            response = self._client.rpc(
                "claim_notification_delivery",
                {"maximum_items": maximum_items, "lease_minutes": lease_minutes},
            ).execute()
            if response.data is None:
                return None
            if not isinstance(response.data, dict):
                raise TypeError("database returned a non-object delivery")
            return self._parse_delivery(response.data)
        except NotificationPersistenceError:
            raise
        except Exception as error:
            raise NotificationPersistenceError("Database notification claim failed") from error

    def complete(
        self,
        delivery_id: str,
        *,
        delivered: bool,
        provider_id: str | None = None,
        error_summary: str | None = None,
        maximum_attempts: int = 5,
    ) -> DeliveryCompletion:
        """Atomically mark a digest sent, retryable, or permanently failed."""
        normalized_id = self._uuid(delivery_id, "delivery_id")
        data = self._call(
            "complete_notification_delivery",
            {
                "target_delivery_id": normalized_id,
                "delivered": delivered,
                "provider_id": provider_id,
                "error_summary": error_summary,
                "maximum_attempts": maximum_attempts,
            },
        )
        status = self._string(data, "status")
        if status not in {"pending", "sent", "failed"}:
            raise NotificationPersistenceError("Database returned an invalid delivery status")
        next_attempt_at = data.get("next_attempt_at")
        if next_attempt_at is not None and not isinstance(next_attempt_at, str):
            raise NotificationPersistenceError("Database returned an invalid retry time")
        return DeliveryCompletion(status=status, next_attempt_at=next_attempt_at)

    def _call(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.rpc(name, params).execute()
            if not isinstance(response.data, dict):
                raise TypeError("database returned a non-object result")
            return response.data
        except NotificationPersistenceError:
            raise
        except Exception as error:
            raise NotificationPersistenceError(
                "Database notification transaction failed"
            ) from error

    @classmethod
    def _parse_delivery(cls, data: dict[str, Any]) -> NotificationDelivery:
        payload = data.get("payload")
        if not isinstance(payload, list) or not payload:
            raise NotificationPersistenceError("Database returned an invalid delivery payload")
        jobs = tuple(cls._parse_job(value) for value in payload)
        return NotificationDelivery(
            id=cls._uuid(cls._string(data, "id"), "delivery.id"),
            dedupe_key=cls._string(data, "dedupe_key"),
            recipient_email=cls._string(data, "recipient_email"),
            subject=cls._string(data, "subject"),
            jobs=jobs,
            attempt_count=cls._count(data, "attempt_count"),
        )

    @classmethod
    def _parse_job(cls, value: Any) -> DigestJob:
        if not isinstance(value, dict):
            raise NotificationPersistenceError("Database returned an invalid digest job")
        return DigestJob(
            job_id=cls._uuid(cls._string(value, "job_id"), "job.id"),
            title=cls._string(value, "title"),
            company=cls._string(value, "company"),
            location=cls._optional_string(value, "location"),
            workplace_type=cls._optional_string(value, "workplace_type"),
            employment_type=cls._optional_string(value, "employment_type"),
            apply_url=cls._http_url(cls._string(value, "apply_url")),
            first_seen_at=cls._string(value, "first_seen_at"),
        )

    @staticmethod
    def _string(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise NotificationPersistenceError(f"Database result has an invalid {key}")
        return value.strip()

    @classmethod
    def _optional_string(cls, data: dict[str, Any], key: str) -> str | None:
        if data.get(key) is None:
            return None
        return cls._string(data, key)

    @staticmethod
    def _count(data: dict[str, Any], key: str) -> int:
        value = data.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise NotificationPersistenceError(f"Database result has an invalid {key} count")
        return value

    @staticmethod
    def _uuid(value: str, name: str) -> str:
        try:
            return str(UUID(value))
        except (AttributeError, TypeError, ValueError) as error:
            raise NotificationPersistenceError(f"Database result has an invalid {name}") from error

    @staticmethod
    def _http_url(value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise NotificationPersistenceError("Database result has an invalid apply_url")
        return value


def render_digest(
    delivery: NotificationDelivery,
    *,
    from_address: str,
    app_base_url: str,
) -> EmailMessage:
    """Render deterministic text and HTML from the stored immutable payload."""
    safe_base_url = app_base_url.rstrip("/")
    rows_html: list[str] = []
    rows_text: list[str] = []
    for job in delivery.jobs:
        metadata = " · ".join(
            value for value in (job.location, job.workplace_type, job.employment_type) if value
        )
        rows_html.append(
            '<li style="margin:0 0 20px">'
            f"<strong>{escape(job.title)}</strong><br>"
            f"<span>{escape(job.company)}</span>"
            + (f"<br><span>{escape(metadata)}</span>" if metadata else "")
            + f'<br><a href="{escape(job.apply_url, quote=True)}">View official application</a>'
            "</li>"
        )
        rows_text.append(
            f"{job.title} — {job.company}"
            + (f"\n{metadata}" if metadata else "")
            + f"\n{job.apply_url}"
        )

    count = len(delivery.jobs)
    intro = (
        f"Launchpad found {count} fresh {'match' if count == 1 else 'matches'} from your watchlist."
    )
    html = (
        '<div style="font-family:Arial,sans-serif;color:#1f201d;max-width:620px">'
        f'<h1 style="font-size:24px">{escape(delivery.subject)}</h1>'
        f'<p>{escape(intro)}</p><ul style="padding-left:20px">{"".join(rows_html)}</ul>'
        f'<p><a href="{escape(safe_base_url, quote=True)}">Open Launchpad</a></p>'
        '<p style="color:#5d625e;font-size:12px">'
        "Freshness is based on Launchpad discovery time. Employer posting dates remain separate."
        "</p></div>"
    )
    text = (
        f"{delivery.subject}\n\n{intro}\n\n"
        + "\n\n".join(rows_text)
        + f"\n\nOpen Launchpad: {safe_base_url}\n\n"
        "Freshness is based on Launchpad discovery time. Employer posting dates remain separate."
    )
    return EmailMessage(
        from_address=from_address,
        to_address=delivery.recipient_email,
        subject=delivery.subject,
        html=html,
        text=text,
        idempotency_key=delivery.dedupe_key,
    )


class ResendEmailProvider:
    """Send transactional email through Resend's idempotent HTTP API."""

    endpoint = "https://api.resend.com/emails"

    def __init__(self, api_key: str, *, client: httpx.Client | None = None) -> None:
        if not api_key.strip():
            raise ValueError("Resend API key is required")
        self._api_key = api_key.strip()
        self._client = client or httpx.Client(timeout=20.0)

    def send(self, message: EmailMessage) -> str:
        """Send one request with the database delivery key as provider idempotency key."""
        try:
            response = self._client.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": message.idempotency_key,
                },
                json={
                    "from": message.from_address,
                    "to": [message.to_address],
                    "subject": message.subject,
                    "html": message.html,
                    "text": message.text,
                },
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            status = (
                error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
            )
            suffix = f" (HTTP {status})" if status is not None else ""
            raise EmailDeliveryError(f"Resend request failed{suffix}") from error
        message_id = data.get("id") if isinstance(data, dict) else None
        if not isinstance(message_id, str) or not message_id.strip():
            raise EmailDeliveryError("Resend returned an invalid message id")
        return message_id.strip()


class NotificationDispatcher:
    """Drain due digest leases while recording every provider outcome."""

    def __init__(
        self,
        repository: NotificationRepository,
        provider: EmailProvider,
        *,
        from_address: str,
        app_base_url: str,
        maximum_attempts: int = 5,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._from_address = from_address
        self._app_base_url = app_base_url
        self._maximum_attempts = maximum_attempts

    def drain(self, *, maximum_deliveries: int = 100) -> DispatchStats:
        """Process due digests until the queue is empty or the run cap is reached."""
        if not 1 <= maximum_deliveries <= 1000:
            raise ValueError("maximum_deliveries must be between 1 and 1000")
        claimed = sent = retry_scheduled = permanently_failed = 0
        for _ in range(maximum_deliveries):
            delivery = self._repository.claim()
            if delivery is None:
                break
            claimed += 1
            message = render_digest(
                delivery,
                from_address=self._from_address,
                app_base_url=self._app_base_url,
            )
            try:
                provider_id = self._provider.send(message)
            except EmailDeliveryError as error:
                completion = self._repository.complete(
                    delivery.id,
                    delivered=False,
                    error_summary=str(error),
                    maximum_attempts=self._maximum_attempts,
                )
                if completion.status == "failed":
                    permanently_failed += 1
                else:
                    retry_scheduled += 1
                continue

            self._repository.complete(
                delivery.id,
                delivered=True,
                provider_id=provider_id,
                maximum_attempts=self._maximum_attempts,
            )
            sent += 1
        return DispatchStats(
            claimed=claimed,
            sent=sent,
            retry_scheduled=retry_scheduled,
            permanently_failed=permanently_failed,
        )
