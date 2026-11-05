# ADR 0011: Paginated incremental matching

## Status

Accepted

## Context

The original Phase 3B RPC returned every open job and full description for one user as a single JSON value. A real 23-company watchlist produced 7,433 open jobs and a 50 MB response. Building that response exceeded the hosted Supabase API timeout, so discovery succeeded but matching and notification queueing failed.

Increasing a timeout would preserve an unbounded request and make every scheduled cycle repeatedly evaluate unchanged jobs. The matching pipeline needs bounded work while retaining stale-write protection and preventing notifications from being queued after an incomplete run.

## Decision

The service-role worker reads missing or stale matches in UUID-keyset pages of 100 jobs. A job is eligible when no result exists or its preference timestamp, preference identity, job content hash, or matcher version is stale. Each page includes the same explicit preference snapshot and at most 100 full job records.

Each evaluated page is upserted through a separate service-role-only transaction. The write locks and rechecks the preference timestamp, ownership, open status, and job content hash. After the final page, a finalization RPC verifies that no eligible candidates remain and removes results for jobs that are no longer open and owned. Notifications are queued only after finalization succeeds.

If a run stops between pages, completed results remain valid and the next run resumes by selecting only missing or stale rows. If preferences or job content change during processing, the affected write or finalization fails safely and a later cycle retries it.

## Consequences

- RPC request and response sizes are bounded independently of watchlist size.
- Unchanged scheduled cycles perform no job reevaluation.
- First-time or preference-wide refreshes require multiple database round trips, but each is retry-safe.
- A job created concurrently behind the current keyset cursor prevents finalization if it is visible before the final check; otherwise it is picked up by the next scheduled cycle.
- ADR 0006 remains the source of truth for match-result shape and stale-write guarantees, but its complete single-request snapshot mechanism is superseded by this paginated protocol.
