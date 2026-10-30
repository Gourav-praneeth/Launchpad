# ADR 0004: Database-backed source configuration

## Status

Accepted

## Context

An operational discovery command needs to select a company source without allowing a caller to combine an arbitrary ATS token with an unrelated database source ID. Environment variables or command-line arguments for both values could accidentally persist jobs under the wrong company.

## Decision

The discovery command accepts only a source UUID. Using the server-only Supabase client, it loads the source type, official URL, and active state from `public.sources`. The adapter factory validates the URL against the selected source type and derives the Greenhouse board token only from the official `boards-api.greenhouse.io` list-jobs endpoint.

Inactive, missing, malformed, and unsupported sources fail before any external request or persistence call. Operational logs contain source IDs, result counts, and safe error codes; they do not include credentials, response bodies, or raw listing validation content.

## Consequences

- The database remains the source of truth for the company-to-source relationship.
- Scheduled jobs need only a source UUID plus server-side Supabase credentials.
- Adding another ATS requires one independent adapter and one explicit factory branch.
- A source must be manually verified and inserted before the worker can monitor it.
