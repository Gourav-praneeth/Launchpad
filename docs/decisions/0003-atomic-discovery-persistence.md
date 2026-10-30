# ADR 0003: Atomic discovery persistence through PostgreSQL

## Status

Accepted

## Context

A discovery run updates several related records: jobs, job events, source health, and the source-check audit trail. Issuing independent PostgREST writes from Python could leave those records inconsistent if a request fails midway. Overlapping scheduled runs could also regress timestamps or overwrite a newer observation with an older response.

## Decision

Persist each source outcome through the service-role-only `persist_discovery_check` PostgreSQL function. One function call is one database transaction. It locks the source row to serialize writes for that source, prefers the external job ID for lookup, falls back to the adapter's deduplication key, preserves `first_seen_at`, and ignores observations older than a job's current `last_seen_at`.

Successful and partial results positively verify only the valid jobs included in the response. Failed checks record source health and an audit record but never update job availability. Phase 2B does not infer that missing listings are closed; closure requires a separate evidence policy in a later phase.

Meaningful persisted listing fields produce a deterministic SHA-256 content hash. A changed hash creates an `updated` event. A positively observed non-open job becomes open and creates a `reopened` event. New jobs create a `first_seen` event in the same transaction.

## Consequences

- The worker needs only one RPC call for a successful, partial, or failed source outcome.
- A transaction failure rolls back all writes from that outcome.
- The RPC is unavailable to anonymous and authenticated browser clients; only the trusted service role can execute it.
- Local execution of migrations requires the Supabase Docker stack or a safe linked development project.
