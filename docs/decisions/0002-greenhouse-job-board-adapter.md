# ADR 0002: Greenhouse Job Board API as the first source adapter

## Status

Accepted

## Context

Launchpad needs one structured, public source implemented end to end before adding more adapters. The source must expose stable job-post identifiers and official application URLs without scraping HTML or bypassing access controls.

## Decision

Use the public Greenhouse Job Board API list-jobs endpoint with `content=true` as the first adapter. Public GET requests need no API credential. The documented job-post `id` is the external identifier. The adapter accepts a manually verified board token, validates each job independently, and reports malformed entries as a partial result rather than discarding valid siblings.

The list endpoint's `updated_at` value is stored only as `source_updated_at`. It is not an employer publication timestamp. `employer_posted_at` remains null because the list response does not document `first_published`.

Routine tests use a checked-in synthetic fixture and `httpx.MockTransport`; they never call a live employer board.

## Consequences

Phase 2A makes no database writes and does not infer employment type, workplace type, or experience level. A later increment will connect normalized results to transaction-safe persistence and source-check records. If trustworthy publication time is needed, a later design can evaluate the per-job detail endpoint and its request-volume tradeoff.
