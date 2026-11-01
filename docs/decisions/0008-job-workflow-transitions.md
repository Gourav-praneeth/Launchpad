# ADR 0008: Database-enforced job workflow transitions

## Status

Accepted

## Context

Phase 4B lets an authenticated user save, dismiss, and record an application from the job feed. These mutations update both a status and its associated timestamp. Implementing those changes as unrelated browser writes could produce contradictory rows, reset historical timestamps during retries, or allow a stale Save request to overwrite an applied state.

## Decision

Expose one authenticated PostgreSQL function, `set_job_workflow_status`, for the Phase 4B mutations. The function runs with the caller's privileges, derives ownership from `auth.uid()`, and remains subject to the existing `user_jobs` Row Level Security policy. Anonymous clients cannot execute it.

The function accepts only `new`, `saved`, `applied`, and `not_interested` as interactive targets. It applies these timestamp rules atomically:

- Saving sets `saved_at` once; an idempotent retry preserves it.
- Unsaving returns a saved job to `new` and clears `saved_at`.
- Applying sets `applied_at` once; an idempotent retry preserves it.
- Dismissing records `not_interested` and clears an active saved timestamp.

Applied, interviewing, rejected, closed, and dismissed records cannot be regressed by a stale action. The Next.js Server Action validates input, verifies the current session again, calls the function, and revalidates the feed. It never accepts a browser-provided user ID.

## Consequences

Workflow timestamps and transitions have one testable source of truth, and retries are safe. Dismissed jobs disappear from active views, while saved and applied jobs remain available in dedicated tabs even after the source listing closes. Phase 4B deliberately does not add notes, interview-stage editing, or restoration of dismissed jobs; those require explicit product behavior in a later increment.
