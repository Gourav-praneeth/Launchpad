# ADR 0001: Authenticated ownership from the first migration

## Status

Accepted

## Context

Launchpad begins as a personal application, but a hosted dashboard still needs access control. Adding ownership after jobs, preferences, interactions, and notifications exist would require invasive schema and policy changes.

## Decision

Use Supabase Auth identities from Phase 1. Companies and preference records carry direct ownership. Related sources, jobs, checks, and events inherit visibility through their company. User-job interactions and notifications carry direct ownership. Row Level Security permits authenticated users to access only their records, while trusted worker writes use the server-only service-role key.

## Consequences

The local database needs an authenticated user before browser CRUD flows can be exercised. The schema is slightly more explicit now, but avoids a disruptive ownership migration before deployment. Service-role credentials must remain outside browser bundles.
