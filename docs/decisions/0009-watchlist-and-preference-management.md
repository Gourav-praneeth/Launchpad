# ADR 0009: Atomic watchlist and explicit preference management

## Status

Accepted

## Context

Phase 4C lets authenticated users configure the two inputs that drive Launchpad: the companies to monitor and the explicit preferences used for deterministic matching. A partially created company without a usable source would be operationally misleading. Accepting arbitrary source URLs would also let the web application create configurations the Python worker refuses to run. Preference changes can make existing match results stale even though their underlying job rows have not changed.

## Decision

The company screen supports the source adapter currently implemented by the worker: an official Greenhouse list-jobs endpoint. PostgreSQL validates the same HTTPS URL shape as the Python source registry. `create_watchlist_company` creates the company and source in one transaction and derives ownership from `auth.uid()`; the browser never provides a user ID. `set_company_monitoring` pauses or resumes the company and all of its sources together. Pausing is non-destructive: jobs, source checks, and freshness timestamps remain intact.

The preference screen exposes only explicit listing-based inputs: target titles, career levels, employment types, locations, workplace types, include and exclude keywords, sponsorship preference, senior-role inclusion, and alert frequency. `update_job_preferences` updates the authenticated user's single preference row and deletes that user's derived `job_matches` rows in the same transaction. The matching worker must then persist a fresh, complete evaluation based on the new preference timestamp.

Both mutation paths are reached through authenticated Next.js Server Actions that validate untrusted form data before calling PostgreSQL. Direct authenticated writes to companies, sources, and preferences are revoked, so clients cannot bypass atomicity or stale-match invalidation. The narrowly scoped security-definer functions derive identity from `auth.uid()`, use an empty search path, and update only rows owned by that identity. Row Level Security continues to scope reads. Anonymous users cannot execute the functions.

## Consequences

The UI cannot create a source configuration the current worker does not understand, and company creation cannot leave a half-written watchlist entry. Additional ATS adapters require an explicit database constraint and UI update alongside the independent worker adapter. Pausing monitoring does not imply that existing jobs are closed. Preference changes temporarily remove derived match labels until the worker runs again, which is honest and avoids presenting stale decisions. Phase 5 must schedule discovery and matching so this refresh happens automatically and must make the selected alert frequency operational.
