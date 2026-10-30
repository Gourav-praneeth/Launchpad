# ADR 0005: Deterministic preference matching

- Status: Accepted
- Date: 2026-10-30

## Context

Launchpad needs to identify relevant new-grad software engineering jobs without resumes, candidate profiling, or opaque ranking. Source metadata is often incomplete, so treating every missing field as either a match or a rejection would hide uncertainty from the user.

Freshness also has a separate product meaning. A newly discovered listing should appear prominently in the feed, but its age must not change whether it satisfies a user's preferences.

## Decision

The Phase 3 matcher is a pure, deterministic Python component. Its only inputs are a normalized `JobListing` and explicit `JobPreferences`. It produces one of three outcomes:

- `matched`: every configured rule has sufficient evidence and no rule rejects the job.
- `review`: no rule rejects the job, but configured metadata is missing or ambiguous.
- `rejected`: at least one rule has clear evidence that the job does not satisfy the preferences.

Every outcome carries stable reason codes and readable evidence. The initial rules cover target titles, career level, employment type, location, workplace type, include/exclude keywords, and explicit sponsorship statements.

Additional semantics:

- Senior, staff, principal, lead, manager, and similar roles are rejected by default. Users must explicitly enable senior roles and include the experienced career level.
- The default employment preference is full-time.
- Multiple include keywords use OR semantics; one matching term is sufficient.
- Exclude keywords always create a rejection.
- Sponsorship is never inferred. A required sponsorship preference with no explicit listing evidence creates a review result.
- Freshness timestamps, resume data, and user behavior are not matcher inputs and cannot alter the result.

## Consequences

- Matching is explainable, repeatable, and straightforward to test.
- Incomplete ATS metadata is surfaced honestly rather than silently guessed.
- Feed ordering remains a separate concern from eligibility.
- Phase 3B can persist preferences and results without embedding business rules in PostgreSQL.
- Some relevant listings will require review until source adapters provide richer metadata or the user refines preferences.
