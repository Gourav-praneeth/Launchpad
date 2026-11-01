# ADR 0007: Authenticated freshness-first dashboard

## Status

Accepted

## Context

The first dashboard must make newly discovered roles useful without weakening Launchpad's timestamp guarantees or exposing another user's companies, jobs, matches, or interactions. It also needs a dependable first-run path: a newly created Auth user cannot be matched until a `user_preferences` row exists.

## Decision

Use Supabase Auth cookie sessions in Next.js. A Next.js proxy refreshes the session, server actions handle sign-in, sign-up, and sign-out, and the dashboard data-access layer verifies claims before querying. Dashboard queries use the public Supabase client and database Row Level Security; the service-role key is never used by the web application.

Create one default `user_preferences` row after each `auth.users` insert with a security-definer database trigger. The defaults retain the MVP's explicit new-grad career levels and senior-role exclusion. The trigger is idempotent, backfills existing Auth users, and is not callable by browser roles.

Order the primary feed by immutable `first_seen_at`. Exclude deterministically rejected results and offer separate matched and review views. Present these timestamps independently:

- `first_seen_at` as Launchpad's discovery time.
- `last_verified_at` as the latest positive availability verification.
- `employer_posted_at` only when the source supplied it; otherwise show that it was not provided.

Do not substitute source update time, scheduler time, or another inferred value for an employer-posted timestamp.

## Consequences

The dashboard can be safely rendered on the server without privileged credentials, and first-time users always have a valid preference record. A local demo requires a running Supabase stack and a user session. The initial feed is deliberately read-only; saved, dismissed, and applied mutations, preference editing, and watchlist management remain later Phase 4 increments.
