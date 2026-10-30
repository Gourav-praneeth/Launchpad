# Launchpad

Launchpad is a freshness-first job discovery application for CS and software engineering new graduates. It monitors a curated watchlist of employers, discovers new listings from official career sources, preserves honest freshness timestamps, and will deliver fast, duplicate-safe notifications based only on explicit user preferences.

> Current status: Phase 3 is complete. Deterministic preference matching and atomic, explainable result persistence are implemented. The authenticated freshness-first dashboard is next.

## Why Launchpad

General job boards can surface listings late or obscure when they were actually discovered. Launchpad is designed around company-first monitoring and four distinct timestamps:

- `employer_posted_at`: a source-provided publication time, when trustworthy.
- `first_seen_at`: when Launchpad first discovered the job; immutable after insertion.
- `last_seen_at`: the latest successful observation of the listing.
- `last_verified_at`: the latest positive availability verification.

Launchpad never labels an inferred timestamp as employer-provided and never treats a failed source check as evidence that jobs closed.

## Current capabilities

- Next.js and TypeScript web foundation with server-safe Supabase clients.
- PostgreSQL schema, migrations, Row Level Security, and authenticated ownership.
- Reusable Python source-adapter contract and normalized job model.
- Greenhouse Job Board API adapter using stable external job IDs.
- Deterministic HTML, text, timestamp, and application-URL normalization.
- Per-listing validation with explicit partial-source results.
- Atomic persistence of jobs, events, source checks, and source health.
- Deduplication by source job ID with a canonical fallback key.
- Immutable `first_seen_at`, stale-run protection, and reopening events.
- Database-backed source selection and an operational discovery command.
- Deterministic matching from explicit preferences with transparent matched, review, and rejected outcomes.
- New-grad career-level rules, senior-role exclusion, metadata filters, keyword rules, and explicit sponsorship handling.
- Atomic match-result persistence with preference and job stale-write protection.
- User-owned match results with read-only browser access enforced by Row Level Security.
- Fixture-based tests that do not depend on live employer career pages.

## Architecture

```text
Official ATS / career source
            │
            ▼
Python discovery adapter ──► normalized JobListing records
            │
            ▼
Service-role-only PostgreSQL RPC
            │
            ├── jobs and freshness timestamps
            ├── first-seen / updated / reopened events
            ├── source-check audit history
            └── source health
            │
            ▼
Supabase PostgreSQL ◄── authenticated Next.js dashboard
```

Repository layout:

- `apps/web`: Next.js application. Browser code receives only the Supabase URL and anon key.
- `worker`: Python 3.12 discovery, normalization, persistence, matching, and notification package.
- `supabase`: PostgreSQL migrations and local Supabase configuration.
- `docs`: product plan and versioned architecture decisions.

Privileged Supabase service-role credentials are used only by the Python worker and must never be exposed to the browser.

## Technology

- Next.js 16, React 19, and TypeScript
- Python 3.12, Pydantic, HTTPX, and Structlog
- PostgreSQL and Supabase Auth
- Pytest, Ruff, mypy, Vitest, ESLint, and Prettier
- GitHub Actions for continuous integration

## Prerequisites

- Node.js 24 or later
- pnpm 11 or later
- Python 3.12
- Docker Desktop for the local Supabase stack

## Local setup

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
pnpm install
python3.12 -m venv .venv
.venv/bin/python -m pip install -e './worker[dev]'
```

Replace the placeholders with values from your own Supabase project. Never place the service-role key in a `NEXT_PUBLIC_` variable or commit it to Git.

Start the local database and apply all migrations:

```bash
pnpm supabase:start
pnpm supabase:reset
```

Lint the schema and run the PostgreSQL persistence tests:

```bash
pnpm supabase:lint
pnpm supabase:test
```

Run the web application:

```bash
pnpm dev
```

The dashboard is available at [http://localhost:3000](http://localhost:3000).

## Verification

Frontend checks:

```bash
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Worker checks:

```bash
.venv/bin/ruff format --check worker
.venv/bin/ruff check worker
.venv/bin/mypy worker/src worker/tests
.venv/bin/pytest worker
```

Routine worker tests use synthetic fixtures and mocked HTTP responses. They do not call live employer sources.

Run one manually verified source by its database UUID:

```bash
.venv/bin/launchpad-worker discover \
  --source-id 30000000-0000-0000-0000-000000000001
```

The source UUID must identify an active row whose URL is the verified official ATS endpoint. The command does not accept a separate Greenhouse board token.

Evaluate every open job owned by one user against that user's stored preferences:

```bash
.venv/bin/launchpad-worker match \
  --user-id 10000000-0000-0000-0000-000000000001
```

The user must have one `public.user_preferences` row. The worker stores one versioned, explainable result per open job. If preferences or job content change during the run, the batch fails safely and should be retried.

## Product constraints

- No resume uploads, parsing, similarity scores, or candidate profiling.
- Matching uses only explicit preferences and job-listing metadata.
- External job IDs are preferred for deduplication; titles alone are never sufficient.
- `first_seen_at` is never reset by an update.
- Source publication, discovery, observation, and verification times remain distinct.
- Failed checks never close jobs or reset their freshness state.
- Notifications must be database-idempotent before delivery automation is enabled.

## Roadmap

- [x] Phase 1 — Project, database, authentication, and quality foundation
- [x] Phase 2A — Greenhouse source adapter and deterministic normalization
- [x] Phase 2B — Atomic persistence, deduplication, events, and source health
- [x] Phase 3 — Explicit-preference matching and transparent match reasons
- [ ] Phase 4 — Freshness-first dashboard and job workflow states
- [ ] Phase 5 — Scheduling, email notifications, retries, and source monitoring
- [ ] Phase 6 — End-to-end MVP validation, deployment, and maintenance docs

See [docs/plan.md](docs/plan.md) for the complete product and technical plan. Meaningful architecture decisions are recorded in [docs/decisions](docs/decisions).

## License

No open-source license has been selected yet. All rights are reserved unless a license is added later.
