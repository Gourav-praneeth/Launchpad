# Notification and automation operations

## Scheduled cycle

`launchpad-worker cycle` performs four bounded stages:

1. Load active sources whose configured cadence and failure backoff are due.
2. Run every source independently and persist each success, partial result, or failure.
3. Refresh deterministic matching for each active watchlist owner and queue missing matches.
4. Claim and deliver due immediate or digest emails.

One source failure does not stop later sources or users. The command exits non-zero after completing the remaining work if a source, matching operation, or email attempt failed. This keeps partial progress while making the GitHub Actions run visibly unhealthy.

For local verification without email credentials:

```bash
.venv/bin/launchpad-worker cycle --skip-email
```

This still calls real configured sources. Routine unit tests use fixtures and mocked HTTP responses instead.

## Queue and digest guarantees

- One notification item exists per user and matching job.
- Only jobs discovered on or after `notifications_enabled_at` qualify.
- Immediate items are available at once.
- Hourly items become available at the next UTC hour.
- Daily items become available at the next UTC day boundary.
- Up to 50 due items for one recipient are grouped into one immutable delivery by default.
- A claimed delivery has a 15-minute lease. A crashed worker can safely reclaim it after the lease.
- The same immutable payload and idempotency key are used for every retry.
- A successful digest marks all of its notification items sent atomically.

## Retry behavior

Source failures use delays of 5, 10, 20, 40, 80, 160, and then at most 360 minutes. The source's normal check cadence still applies, so the later of cadence eligibility and backoff controls the next run. Failed checks never close jobs or change `first_seen_at`.

Email failures use the same bounded exponential pattern and become terminal after five attempts by default. Safe logs contain the provider status category but not provider response bodies, API keys, or email contents. Resend supports an `Idempotency-Key` header on `POST /emails`; Launchpad uses the database delivery key for that header.

## Required configuration

GitHub Actions secrets:

- `LAUNCHPAD_SUPABASE_URL`
- `LAUNCHPAD_SUPABASE_SERVICE_ROLE_KEY`
- `LAUNCHPAD_RESEND_API_KEY`

GitHub Actions variables:

- `LAUNCHPAD_EMAIL_FROM`
- `LAUNCHPAD_APP_BASE_URL`

Use a Resend-verified domain or sender for `LAUNCHPAD_EMAIL_FROM`. Never use the service-role or Resend key in a `NEXT_PUBLIC_` variable.

## Recovery checks

- A red GitHub Actions run can still contain successful work for unaffected sources.
- Inspect `sources.last_error`, `consecutive_failures`, `backoff_until`, and the latest `source_checks` rows for source failures.
- Inspect `notification_deliveries.status`, `attempt_count`, `next_attempt_at`, and `last_error` with service-role tooling for delivery failures.
- Use `launchpad-worker deliver` to retry only due email without fetching career sources.
- Do not manually change a sent delivery back to pending; provider and database idempotency assume sent state is final.

References: [Resend idempotency keys](https://resend.com/docs/dashboard/emails/idempotency-keys) and [GitHub scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
