# ADR 0010: Idempotent scheduled discovery and email digests

## Status

Accepted

## Context

Phase 5 must run discovery without terminal commands, continue through partial source failures, refresh matches, and send timely email without duplicates. A scheduler can overlap or retry runs. A provider request can succeed while the worker loses the response. User preferences also promise immediate, hourly, or daily delivery, so delaying a series of individual messages would not be a real digest.

## Decision

GitHub Actions triggers `launchpad-worker cycle` four times per hour and permits only one scheduled cycle at a time. PostgreSQL determines which active sources are due from their configured cadence, last actual attempt, and retry backoff. Failed and partial checks increase a bounded exponential backoff; a successful check clears it. Each source and each user is processed independently so one failure does not prevent other discovery, matching, or queue work.

After a successful deterministic match snapshot, `queue_match_notifications` inserts one notification item per user and job with a stable unique key. A `notifications_enabled_at` watermark prevents Phase 5 deployment or a new account from alerting on jobs discovered before notifications were enabled. Alert frequency determines when items become available.

`claim_notification_delivery` atomically groups due items for one user into a digest, stores an immutable job snapshot, attaches the items to that delivery, and leases it. Retries reuse the stored payload and delivery key. The worker sends this key in Resend's `Idempotency-Key` header, records the provider message ID on success, and schedules bounded exponential retries on safe provider failures. A delivery becomes terminally failed after the configured attempt limit. Authenticated browser clients can read their notification item status but cannot create queue items, inspect delivery recipient data, claim work, or complete deliveries.

## Consequences

Database uniqueness protects queue creation, delivery leases protect concurrency, and Resend idempotency protects the external side effect when a response is lost. Hourly and daily settings produce grouped messages. Stored payloads intentionally preserve what the user was told even if a job changes before a retry. Email delivery requires a verified Resend sender, API key, service-role key, and deployed application URL. GitHub scheduling is convenient for the personal MVP but its timing is not exact; measured attempt and delivery timestamps remain the source of truth.
