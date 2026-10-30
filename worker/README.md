# Launchpad worker

This Python 3.12 package owns source fetching, normalization, deduplication orchestration, deterministic matching, and notification queuing.

Phase 2A adds a Greenhouse Job Board API adapter with typed normalized output, per-item validation, explicit partial results, canonical application URLs, and fixture-based tests.

Phase 2B adds transaction-safe persistence. `DiscoveryRunner` records either a successful/partial fetch or a sanitized source failure through `DiscoveryRepository`. The `persist_discovery_check` PostgreSQL function commits jobs, events, source health, and the source-check audit record together. It never treats a failed check as evidence that a job closed.

Phase 3A adds a pure deterministic matcher. It evaluates normalized listings against explicit title, career-level, employment, location, workplace, keyword, and sponsorship preferences. Missing configured metadata produces a review result; clear conflicts produce a rejection. Freshness timestamps and resume data are intentionally outside the matching decision.

The worker requires server-only Supabase credentials using the `LAUNCHPAD_` environment prefix. It must never be embedded in or imported by the web client.

## Greenhouse adapter example

```python
from launchpad_worker.sources import GreenhouseJobSource

result = GreenhouseJobSource("verified-board-token").fetch_jobs()
```

Only use a board token that has been manually verified against the employer's official careers page. A successful empty result has no jobs and no issues; a result with rejected items sets `is_partial`; a request or top-level response failure raises `SourceFetchError`.

## Persistence example

```python
from launchpad_worker.database import create_database_client
from launchpad_worker.discovery import DiscoveryRunner
from launchpad_worker.persistence import DiscoveryRepository

client = create_database_client(settings)
runner = DiscoveryRunner(DiscoveryRepository(client))
stats = runner.run(source_id=source_id, source=source)
```

Apply all Supabase migrations before running discovery. The persistence RPC is intentionally executable only with the server-side service-role credential.

## Operational discovery command

After manually verifying and inserting an active `public.sources` row, run it by UUID:

```bash
.venv/bin/launchpad-worker discover \
  --source-id 30000000-0000-0000-0000-000000000001
```

The command loads the source type and official URL from PostgreSQL, constructs the independent adapter, and records the successful, partial, or failed result. It does not accept a separate board token, which prevents jobs from being associated with the wrong configured company.

## Matching example

```python
from launchpad_worker.matching import JobMatcher, JobPreferences

preferences = JobPreferences(
    locations=("San Francisco", "New York"),
    workplace_types=("remote", "hybrid"),
    include_keywords=("backend", "distributed systems"),
)
result = JobMatcher().evaluate(listing, preferences)
```

`result.status` is `matched`, `review`, or `rejected`, and its reason collections provide stable codes plus readable evidence. Include keywords use OR semantics. Senior roles are excluded by default, and unknown sponsorship is never treated as available.
