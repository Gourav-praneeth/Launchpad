# Launchpad

Launchpad is a freshness-first job discovery application for new-graduate software engineers. It monitors a curated company watchlist, preserves honest discovery and verification timestamps, applies deterministic preference rules, and eventually sends idempotent email alerts.

Phase 1 establishes the project, security, database, and quality foundations. It intentionally does not fetch jobs or send notifications yet.

## Architecture

- `apps/web`: Next.js and TypeScript application. Browser code uses only the Supabase URL and anon key. Privileged operations stay server-side.
- `worker`: Python 3.12 package for source discovery, normalization, persistence, matching, and notification orchestration in later phases.
- `supabase`: PostgreSQL migrations and local Supabase configuration.
- `docs`: versioned product plan and architecture decisions.

## Prerequisites

- Node.js 24 or later
- pnpm 11 or later
- Python 3.12
- Supabase CLI for local database commands
- Docker Desktop when running Supabase locally

## Local setup

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
pnpm install
python3.12 -m venv .venv
.venv/bin/python -m pip install -e './worker[dev]'
```

Replace the placeholders in `.env` with values from your own Supabase project. The service-role key is server-only and must never be copied to a `NEXT_PUBLIC_` variable.

Run the web application:

```bash
pnpm dev
```

Run all local quality checks:

```bash
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
.venv/bin/ruff check worker
.venv/bin/mypy worker/src worker/tests
.venv/bin/pytest worker
```

## Database

The first migration creates the complete MVP-oriented schema, authentication ownership, row-level security, timestamp safeguards, source-check history, and database-backed deduplication constraints.

With the Supabase CLI installed and Docker running:

```bash
pnpm supabase:start
pnpm supabase:reset
```

The frontend uses authenticated owner-scoped access. The discovery worker uses the service-role key and is responsible for trusted writes to sources, jobs, events, source checks, and notification delivery state.

## Product constraints

- No resume uploads, parsing, scoring, or resume-derived matching.
- `first_seen_at` is immutable after insertion.
- Employer posting time is stored separately from discovery time.
- A failed or partial source check is never evidence that a job closed.
- Routine tests use fixtures and mocks rather than live career pages.
