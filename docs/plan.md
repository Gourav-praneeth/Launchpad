# Launchpad — Product & Technical Plan

> **Working name:** Launchpad  
> **Product:** A freshness-first job discovery app for new-graduate software engineers  
> **Initial use:** Personal tool  
> **Primary goal:** Discover relevant new-grad job openings at selected companies as soon as possible after they become publicly available, then notify the user quickly.

---

## 1. Product vision

Launchpad is a personal early-warning system for new-grad job openings. It monitors a curated list of employers, detects new or changed listings, filters them using explicit job-search preferences, and sends timely alerts with links to the employer's application page.

### Core promise

**Find relevant new-grad software engineering openings early, without manually checking dozens of career pages every day.**

### Product principles

1. **Freshness first:** prioritize when a listing was first detected, while distinguishing that from the employer's actual publication time.
2. **Preference-based discovery, not resume-based recommendations:** job visibility must never depend on uploading, parsing, scoring, or matching a resume.
3. **Trustworthy information:** show where a job came from, when it was detected, when it was last checked, and what is known about its status.
4. **Low noise:** avoid irrelevant roles, duplicate alerts, and unsupported claims about eligibility.
5. **Apply through the source:** send users to the official employer application page rather than automatically applying on their behalf.
6. **Personal-first implementation:** start with a small, dependable tool before considering a public multi-user product.

---

## 2. Target user and scope

### Initial audience

Computer Science / Software Engineering new graduates looking for full-time, early-career roles.

### Initial use case

The user maintains a list of target companies. Launchpad checks their supported careers pages or job feeds, detects new listings, identifies likely new-grad or entry-level software engineering roles, and sends an alert.

### In scope for the MVP

- Add, edit, pause, and remove monitored companies.
- Monitor supported company career pages and structured job feeds.
- Normalize job listings into a common schema.
- Detect new listings and meaningful changes.
- Filter using explicit preferences, not a resume.
- Sort the feed by first-detected time, newest first.
- Display the employer-reported posting date separately when available.
- Show the official application link and source.
- Send email alerts for new matching jobs.
- Save jobs and manually track application status.
- Track source health, failed checks, and notification delivery.

### Out of scope for the MVP

- Resume uploads, resume parsing, resume scoring, or resume-based job matching.
- AI-generated resumes or cover letters.
- Automatic application submission or CAPTCHA/access-control bypass.
- Mobile apps and browser extensions.
- Public social features or paid subscriptions.
- Broad, unbounded scraping of the entire web.
- Claims that a job is guaranteed to be seen before other applicants.
- Sponsorship or eligibility guarantees without reliable source evidence.

---

## 3. Job discovery and filtering rules

### Jobs must NOT be selected or ranked using a resume

The app must not require a resume. Do not store resume files, parse resume content, calculate resume similarity, or use resume-derived skills to decide which jobs appear.

Use only the following explicit user preferences and listing data:

- Target role categories and job-title keywords.
- Career level: new grad, university graduate, entry-level, or early career.
- Employment type, initially full-time.
- Preferred locations and remote/hybrid/on-site preference.
- Graduation window, if the user chooses to provide one.
- Optional work-authorization/sponsorship preference.
- Explicit include/exclude keywords and company watchlist.

A candidate can change these preferences at any time. The app should explain why a listing matches, for example: “Title matches Software Engineer; classified as entry-level; location matches your preferences.”

### Initial matching logic

Use transparent rules before introducing machine learning:

1. Include roles with relevant titles such as Software Engineer, Software Developer, Backend Engineer, or New Grad Software Engineer.
2. Include listings identified as new grad, university graduate, entry-level, associate, or early career.
3. Exclude clear senior/staff/principal/lead/manager roles unless the user explicitly enables them.
4. Prefer full-time roles for the initial MVP.
5. Apply the user's selected location and work-arrangement preferences when reliable information exists.
6. If experience level, sponsorship, or eligibility is unclear, mark it “Unknown” or “Review needed”; do not silently assume.
7. Preserve the original title and description so filtering decisions can be checked.
8. Keep freshness sorting separate from match eligibility. By default, show matching jobs newest detected first.

The matching system should be deterministic and testable. An LLM is not necessary for the initial version.

---

## 4. Freshness and timestamp semantics

Never present “first detected” as if it were the actual publication time.

Each job should distinguish:

- **Employer-reported posting time:** timestamp provided by the source, if available and trustworthy.
- **First detected time (`first_seen_at`):** first time Launchpad successfully observed the listing.
- **Last seen time (`last_seen_at`):** most recent successful observation of the listing.
- **Last verified time (`last_verified_at`):** last time its availability or application link was checked.
- **Source check time:** when the source was last checked, including failed attempts.
- **Status confidence:** open, closed, or uncertain, based on source evidence.

UI examples:

- “First detected 4 minutes ago”
- “Employer posted date: Oct 28” (only when supplied by the source)
- “Posting date unavailable”
- “Last verified open 12 minutes ago”
- “Status uncertain — source could not be checked”

A job discovered recently may have been published earlier. The app should communicate this clearly.

---

## 5. MVP features

### 5.1 Company watchlist

- Company name.
- Official careers URL.
- Source type and source endpoint, where applicable.
- Active/paused status.
- Last successful check and most recent error.
- Desired polling interval, within source limits.

### 5.2 Discovery worker

- Fetch listings from supported sources.
- Normalize source-specific fields.
- Deduplicate records.
- Save new jobs and meaningful updates.
- Record discovery events.
- Run matching against explicit user preferences.
- Queue notifications only for qualifying new listings.

### 5.3 Freshness-first dashboard

Each job card should display:

- Job title and company.
- Location and work arrangement, when available.
- Employment type and career-level classification.
- First-detected time.
- Employer-reported posting date, if available.
- Last verification and current status confidence.
- Source name.
- Official application link.
- Save / mark applied / mark closed controls.
- A short, transparent match explanation.

Default sort: `first_seen_at DESC`.

### 5.4 Notifications

Start with email rather than push notifications.

Email should contain:

- Job title and company.
- Location, if available.
- First-detected time.
- Employer-reported posting date, if available.
- Brief reason it matched the user's explicit preferences.
- Link to the official application page.
- Link to view the listing in Launchpad.

Requirements:

- Send one alert per qualifying new job per user.
- Use a unique deduplication key.
- Retry transient failures safely.
- Do not send a duplicate after a confirmed successful send.
- Record queued, sent, and failed status.

### 5.5 Saved jobs and application tracking

Simple statuses:

- New
- Saved
- Applied
- Interviewing
- Rejected
- Closed
- Not interested

Track status manually for the personal MVP. Do not automate application submission.

---

## 6. Company-first source strategy

Start with a manually curated set of approximately 20–30 employers. Begin with 5–10 and expand after the first adapters are reliable.

### Source priority

1. Official employer careers pages.
2. Public, structured ATS job feeds/endpoints that the employer or platform makes available and that are permitted by the applicable terms.
3. Individual page adapters for high-priority companies not covered by supported feeds.
4. Licensed job APIs only if they become necessary and fit the budget and terms.

### Initial adapter candidates

Investigate these source categories and validate current documentation, access requirements, and terms before implementation:

- Greenhouse-hosted job boards: https://developers.greenhouse.io/
- Lever-hosted job boards: https://hire.lever.co/developer/
- Other employer-specific career pages and ATS providers as needed.

Do not assume every company using an ATS exposes the same fields or public endpoint. Verify each employer's source individually.

### Source adapter design

Every adapter should produce a common normalized listing object, regardless of its original format.

Example Python interface:

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class JobListing:
    external_id: str | None
    title: str
    location: str | None
    apply_url: str
    posted_at: datetime | None
    description: str | None
    employment_type: str | None
    workplace_type: str | None


class JobSource:
    def fetch_jobs(self) -> list[JobListing]:
        raise NotImplementedError
```

Implement one adapter end-to-end before adding more. Prefer stable structured data over brittle HTML parsing. Respect site terms, robots.txt where applicable, rate limits, and access controls. Do not bypass CAPTCHA or other restrictions.

### Polling strategy

- Begin with a conservative interval such as every 15–60 minutes, subject to each source's terms and technical limits.
- Poll high-priority sources more frequently only where permitted and reliable.
- Use backoff after errors.
- Add jitter to avoid synchronized requests.
- Log every attempt, including failures.
- Do not interpret a failed or partial fetch as evidence that jobs have closed.
- Scheduled platforms may not run at the exact requested time; measure actual intervals.

---

## 7. Architecture

### Recommended stack

| Layer            | Choice                                         | Purpose                                  |
| ---------------- | ---------------------------------------------- | ---------------------------------------- |
| Frontend         | Next.js + TypeScript                           | Responsive web dashboard                 |
| Database         | Supabase / PostgreSQL                          | Structured listings, events, preferences |
| Discovery worker | Python                                         | Fetch, normalize, deduplicate, match     |
| Scheduling       | GitHub Actions initially, or another scheduler | Trigger worker runs                      |
| Email            | An email provider such as Resend               | Send alerts                              |
| Frontend hosting | Vercel or local development initially          | Host dashboard                           |
| Tests            | pytest + source fixtures                       | Validate adapters and discovery logic    |

The personal MVP can be developed locally before adding hosting. Keep the worker independent of the frontend.

### Data flow

1. Scheduler triggers the discovery worker.
2. Worker loads active sources.
3. Each source adapter fetches the current listings.
4. Worker normalizes and validates returned data.
5. Worker finds existing jobs using source IDs or fallback deduplication.
6. New jobs are inserted and `first_seen_at` is set once.
7. Existing jobs are updated; meaningful changes generate `job_events`.
8. New jobs are checked against explicit user preferences.
9. Matching jobs create notification records.
10. Email sender delivers alerts and records the result.
11. Dashboard reads the jobs, source health, and application status from PostgreSQL.

---

## 8. Database schema

Use PostgreSQL with UUID primary keys and UTC timestamps (`TIMESTAMPTZ`).

### 8.1 `companies`

| Column        | Type        | Notes                 |
| ------------- | ----------- | --------------------- |
| `id`          | UUID PK     | Company identifier    |
| `name`        | TEXT        | Company name          |
| `careers_url` | TEXT        | Official careers page |
| `is_active`   | BOOLEAN     | Default true          |
| `created_at`  | TIMESTAMPTZ | Creation time         |
| `updated_at`  | TIMESTAMPTZ | Last edit             |

### 8.2 `sources`

| Column                   | Type                 | Notes                              |
| ------------------------ | -------------------- | ---------------------------------- |
| `id`                     | UUID PK              | Source identifier                  |
| `company_id`             | UUID FK              | References `companies.id`          |
| `source_type`            | TEXT                 | e.g. `greenhouse`, `lever`, `html` |
| `source_url`             | TEXT                 | Endpoint or page URL               |
| `is_active`              | BOOLEAN              | Whether source is monitored        |
| `check_interval_minutes` | INTEGER              | Desired interval                   |
| `last_attempt_at`        | TIMESTAMPTZ          | Last attempt, successful or not    |
| `last_success_at`        | TIMESTAMPTZ nullable | Last successful fetch              |
| `last_error`             | TEXT nullable        | Latest safe-to-log error summary   |
| `created_at`             | TIMESTAMPTZ          | Creation time                      |

### 8.3 `jobs`

| Column               | Type                 | Notes                                                              |
| -------------------- | -------------------- | ------------------------------------------------------------------ |
| `id`                 | UUID PK              | Internal job identifier                                            |
| `company_id`         | UUID FK              | References `companies.id`                                          |
| `source_id`          | UUID FK              | References `sources.id`                                            |
| `external_job_id`    | TEXT nullable        | ID provided by source                                              |
| `title`              | TEXT                 | Original job title                                                 |
| `normalized_title`   | TEXT                 | For matching and dedupe                                            |
| `location`           | TEXT nullable        | Original location                                                  |
| `workplace_type`     | TEXT nullable        | Remote, hybrid, on-site, unknown                                   |
| `employment_type`    | TEXT nullable        | Full-time, internship, unknown                                     |
| `experience_level`   | TEXT                 | New grad, entry-level, early-career, experienced, unknown          |
| `description`        | TEXT nullable        | Listing description or normalized excerpt                          |
| `apply_url`          | TEXT                 | Official application URL                                           |
| `employer_posted_at` | TIMESTAMPTZ nullable | Source-reported time                                               |
| `first_seen_at`      | TIMESTAMPTZ          | Set on first successful detection; never reset on ordinary updates |
| `last_seen_at`       | TIMESTAMPTZ          | Updated on successful observation                                  |
| `last_verified_at`   | TIMESTAMPTZ nullable | Last positive availability verification                            |
| `status`             | TEXT                 | `open`, `closed`, `uncertain`                                      |
| `content_hash`       | TEXT nullable        | Detect meaningful content changes                                  |
| `created_at`         | TIMESTAMPTZ          | Record creation                                                    |
| `updated_at`         | TIMESTAMPTZ          | Last update                                                        |

**Deduplication:** Prefer a unique constraint on `(source_id, external_job_id)` when the external ID is available. For listings without an ID, use a normalized canonical URL or a carefully designed fallback key. Do not deduplicate by title alone.

### 8.4 `job_events`

| Column        | Type        | Notes                                                             |
| ------------- | ----------- | ----------------------------------------------------------------- |
| `id`          | UUID PK     | Event identifier                                                  |
| `job_id`      | UUID FK     | References `jobs.id`                                              |
| `event_type`  | TEXT        | `first_seen`, `updated`, `closed`, `reopened`, `status_uncertain` |
| `detected_at` | TIMESTAMPTZ | When observed                                                     |
| `details`     | JSONB       | Before/after details where useful                                 |

### 8.5 `user_preferences`

For the initial personal app, use one preferences record. This table makes later multi-user support easier.

| Column                   | Type           | Notes                                        |
| ------------------------ | -------------- | -------------------------------------------- |
| `id`                     | UUID PK        | Preference record                            |
| `target_titles`          | JSONB          | Explicit title categories/keywords           |
| `career_levels`          | JSONB          | New grad, entry-level, early career          |
| `employment_types`       | JSONB          | Initially full-time                          |
| `locations`              | JSONB          | User-selected locations                      |
| `workplace_types`        | JSONB          | Remote, hybrid, on-site                      |
| `graduation_window`      | JSONB nullable | Optional, user-entered                       |
| `sponsorship_preference` | TEXT nullable  | `required`, `not_required`, `any`, `unknown` |
| `include_keywords`       | JSONB          | Optional explicit terms                      |
| `exclude_keywords`       | JSONB          | Optional explicit terms                      |
| `alert_frequency`        | TEXT           | Immediate, hourly digest, daily digest       |
| `updated_at`             | TIMESTAMPTZ    | Last update                                  |

No resume-derived fields should exist in this table.

### 8.6 `user_jobs`

| Column               | Type                 | Notes                                                               |
| -------------------- | -------------------- | ------------------------------------------------------------------- |
| `id`                 | UUID PK              | Interaction record                                                  |
| `job_id`             | UUID FK              | References `jobs.id`                                                |
| `saved_at`           | TIMESTAMPTZ nullable | Saved time                                                          |
| `application_status` | TEXT                 | New, saved, applied, interviewing, rejected, closed, not interested |
| `applied_at`         | TIMESTAMPTZ nullable | Application date                                                    |
| `notes`              | TEXT nullable        | Personal notes                                                      |
| `updated_at`         | TIMESTAMPTZ          | Last edit                                                           |

For a single-user app, this can be simplified. If authentication is added, include `user_id`, enforce unique `(user_id, job_id)`, and apply Supabase Row Level Security.

### 8.7 `notifications`

| Column          | Type                 | Notes                    |
| --------------- | -------------------- | ------------------------ |
| `id`            | UUID PK              | Notification identifier  |
| `job_id`        | UUID FK              | Associated job           |
| `channel`       | TEXT                 | Email initially          |
| `dedupe_key`    | TEXT UNIQUE          | Prevent duplicate sends  |
| `status`        | TEXT                 | Pending, sent, failed    |
| `attempt_count` | INTEGER              | Number of attempts       |
| `created_at`    | TIMESTAMPTZ          | Queued time              |
| `sent_at`       | TIMESTAMPTZ nullable | Successful delivery time |
| `last_error`    | TEXT nullable        | Safe error summary       |

For a future multi-user product, add `user_id` to notifications and include it in the deduplication strategy.

### Useful indexes

- `jobs(first_seen_at DESC)` for the freshness feed.
- `jobs(company_id)` for company filters.
- `jobs(status)` for open/closed filtering.
- `jobs(source_id, external_job_id)` for source-level lookups and deduplication.
- `job_events(job_id, detected_at DESC)` for event history.
- `notifications(status, created_at)` for delivery retries.

---

## 9. Project structure

```text
launchpad/
├── apps/
│   └── web/                     # Next.js dashboard
├── worker/
│   ├── sources/
│   │   ├── base.py
│   │   ├── greenhouse.py
│   │   ├── lever.py
│   │   └── html_source.py
│   ├── discovery.py
│   ├── normalize.py
│   ├── deduplicate.py
│   ├── matching.py
│   ├── notifications.py
│   ├── database.py
│   └── tests/
├── database/
│   └── migrations/
├── .github/
│   └── workflows/
│       └── discover.yml
├── .env.example
├── .gitignore
└── README.md
```

Keep credentials in environment variables. Never commit secrets or expose the Supabase service-role key to client-side code.

---

## 10. Discovery worker pseudocode

```python
def run_discovery(source):
    result = source.fetch_jobs()

    # A successful empty result is different from a failed fetch.
    for listing in result:
        job_data = normalize_listing(listing)
        existing_job = find_existing_job(
            source_id=source.id,
            external_id=job_data.external_id,
            apply_url=job_data.apply_url,
        )

        if existing_job is None:
            job = save_new_job(job_data)

            # Uses only explicit user preferences and listing data.
            if matches_preferences(job):
                queue_alert_once(job)
        else:
            changes = update_existing_job(existing_job, job_data)
            if changes:
                record_job_event(existing_job.id, changes)

    record_successful_check(source)
```

This is illustrative pseudocode. Production code should handle transactions, partial source failures, rate limits, retries, timeouts, malformed listings, and notification idempotency.

---

## 11. Practical four-week roadmap

### Week 1 — Foundation

- Create the Git repository and project structure.
- Set up Python and Supabase.
- Create `companies`, `sources`, and `jobs`.
- Add 5–10 target companies.
- Implement one structured source adapter.
- Save jobs and verify repeated runs do not create duplicates.

**Milestone:** A worker can fetch and persist listings reliably.

### Week 2 — Discovery and freshness

- Implement a second source adapter.
- Add normalization and fallback deduplication.
- Record first-seen and last-seen timestamps.
- Add job events and content hashing.
- Implement deterministic new-grad SWE filters.
- Build the basic freshness-first feed.

**Milestone:** The app distinguishes new listings from existing listings that changed.

### Week 3 — Scheduling and alerts

- Configure scheduled worker runs.
- Add email notifications.
- Add unique dedupe keys, retries, and delivery status.
- Track source failures and last successful checks.
- Ensure source failures never mark every job closed.

**Milestone:** New matching jobs generate reliable, non-duplicated alerts.

### Week 4 — Personal workflow and validation

- Expand to 20–30 selected employers.
- Add saved/applied statuses and basic filters.
- Compare app discoveries against manual checks.
- Measure alert delay, match precision, source coverage, and duplicate rate.
- Fix the largest reliability gaps before adding features.

**Milestone:** The app is useful enough to support the user's real job search.

---

## 12. Metrics and validation

Suggested initial targets—not industry benchmarks:

| Metric                               |                              Initial target |
| ------------------------------------ | ------------------------------------------: |
| Companies monitored                  |                                       20–30 |
| Working source adapters              |                                         2–3 |
| Duplicate notifications              |                                           0 |
| Source checks with recorded outcomes |                                        100% |
| Alerts delivered after detection     | Within 2 minutes for normal successful runs |
| Irrelevant jobs in alerts            |                                   Under 15% |
| Application links                    |        Validated where technically feasible |

Measure two different delays:

1. **Detection delay:** the difference between a trustworthy source publication timestamp and `first_seen_at`. If the source timestamp is missing or unreliable, mark this metric unavailable.
2. **Notification delay:** the time between `first_seen_at` and successful notification delivery.

Also measure source coverage, failed checks, false positives, stale links, and how often alerts lead to opening or saving a job.

The product's advantage should be demonstrated through actual comparisons with the user's existing job-search workflow—not assumed.

---

## 13. Risks and mitigations

| Risk                                          | Mitigation                                                                  |
| --------------------------------------------- | --------------------------------------------------------------------------- |
| Career pages change their HTML                | Prefer structured feeds; test adapters with saved fixtures                  |
| Source blocks or limits requests              | Respect terms and rate limits; back off; disable unsupported sources        |
| Scheduler runs late                           | Measure actual timing; choose a scheduler appropriate to required frequency |
| Duplicates across sources                     | Canonicalize URLs and use external IDs where available                      |
| Incorrect new-grad classification             | Use transparent rules and a manual-review state                             |
| Unclear sponsorship requirements              | Show unknown rather than guessing                                           |
| Listing appears closed                        | Verify cautiously; distinguish failed checks from closure                   |
| Repeated email alerts                         | Use database-backed unique dedupe keys and safe retry handling              |
| Secrets exposed                               | Use environment variables and server-side credentials only                  |
| Resume-based recommendations creep into scope | Keep resume data out of the product and matching pipeline                   |

---

## 14. Decisions to preserve

- **Target audience:** CS / SWE new grads.
- **Discovery strategy:** company-first, curated employer list.
- **Product ambition:** personal tool first; consider public launch only after validation.
- **Core differentiator:** freshness-first discovery and timely notifications.
- **Job filtering:** explicit preferences and listing metadata only; never based on a resume.
- **Initial interface:** responsive web dashboard.
- **Initial notifications:** email.
- **Initial implementation:** Python worker + PostgreSQL/Supabase + Next.js.
- **Initial scale:** 5–10 companies during development, then approximately 20–30.
- **Initial success criterion:** reliably discover relevant listings, avoid duplicate alerts, and measure real detection and notification latency.

## 15. Immediate next steps

1. Create the repository and local Python environment.
2. Create the Supabase project and first schema migration.
3. Choose one employer with a supported structured job feed.
4. Build and test the first source adapter.
5. Confirm duplicate-safe persistence and timestamp semantics.
6. Add a second adapter.
7. Implement explicit-preference filtering.
8. Build the dashboard only after the discovery pipeline is working.

**Guiding principle:** prove that Launchpad can reliably discover relevant jobs early. Keep the MVP narrow, the timestamps honest, and the matching rules transparent.

---

## 16. Implementation decisions

- **Phase 1:** Authenticated ownership and Row Level Security are part of the initial schema. See `docs/decisions/0001-authentication-and-ownership.md`.
- **Phase 2A:** Greenhouse Job Board API is the first source adapter. Its list response's `updated_at` is preserved as a source-update timestamp and is never presented as `employer_posted_at`. Tests use saved synthetic responses rather than live career pages. See `docs/decisions/0002-greenhouse-job-board-adapter.md`.
- **Phase 2B:** A service-role-only PostgreSQL RPC atomically persists jobs, job events, source health, and source-check history. Runs are serialized per source, stale overlapping results cannot regress jobs, and failed checks never close jobs. See `docs/decisions/0003-atomic-discovery-persistence.md`.
