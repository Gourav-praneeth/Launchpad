# ADR 0006: Atomic match-result persistence

- Status: Accepted
- Date: 2026-10-30

## Context

Phase 3A made eligibility decisions deterministic, but persisted results can still become misleading if a preference or job changes between loading and writing. The dashboard and later notification pipeline need one explainable result per user/job pair without accepting stale or incomplete batches.

Derived match results also should not be writable by browser clients. They must reflect the versioned server-side matcher rather than arbitrary client input.

## Decision

Store derived decisions in `public.job_matches`, keyed uniquely by user and job. Each row preserves:

- the matched, review, or rejected status;
- classified career level and sponsorship status;
- separate match, review, and rejection reason arrays;
- the preference update timestamp and job content hash used as input;
- a matcher version and evaluation timestamp.

The Python worker loads a complete preference/open-job snapshot through a service-role-only RPC, evaluates it with the Phase 3A matcher, and writes the complete batch through a second service-role-only transaction.

The write transaction rejects the entire batch when:

- preferences changed after they were loaded;
- any job content hash changed after it was loaded;
- a result references an unavailable or unowned job;
- results do not cover every currently open owned job exactly once;
- a decision or reason collection has an invalid shape.

Authenticated clients may read their own results through Row Level Security but cannot insert, update, or delete derived decisions. Re-running the worker upserts the user/job pair and removes obsolete results that are outside the current open-job snapshot.

## Consequences

- The dashboard can display transparent reasons without recalculating matching in browser code.
- Notification automation can consume a stable, versioned decision table in Phase 5.
- Concurrent discovery or preference edits cause a safe failed run that can be retried instead of mixed-version output.
- Matching currently runs as an explicit worker command. Scheduling it after discovery and preference changes belongs to the later automation phase.
- Each run evaluates the complete open-job snapshot. This is intentionally simple for MVP scale; batching can be introduced later with an explicit snapshot identifier if needed.
