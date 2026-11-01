begin;

create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;

select plan(25);

insert into auth.users (id, email)
values ('10000000-0000-0000-0000-000000000041', 'alerts@launchpad.test');

update public.user_preferences
set id = '50000000-0000-0000-0000-000000000041',
    notifications_enabled_at = '2026-11-01T00:00:00Z',
    alert_frequency = 'immediate'
where user_id = '10000000-0000-0000-0000-000000000041';

insert into public.companies (id, owner_id, name, careers_url)
values (
  '20000000-0000-0000-0000-000000000041',
  '10000000-0000-0000-0000-000000000041',
  'Automation Fixture',
  'https://automation.example.test/careers'
);

insert into public.sources (
  id,
  company_id,
  source_type,
  source_url,
  check_interval_minutes
)
values (
  '30000000-0000-0000-0000-000000000041',
  '20000000-0000-0000-0000-000000000041',
  'greenhouse',
  'https://boards-api.greenhouse.io/v1/boards/automation-fixture/jobs',
  15
);

insert into public.source_checks (
  source_id,
  started_at,
  completed_at,
  outcome,
  error_code,
  error_summary
)
values (
  '30000000-0000-0000-0000-000000000041',
  '2026-11-01T01:00:00Z',
  '2026-11-01T01:00:01Z',
  'failed',
  'request_failed',
  'Fixture timeout'
);

select is(
  (select consecutive_failures from public.sources where id = '30000000-0000-0000-0000-000000000041'),
  1,
  'a failed source check increments the retry counter'
);
select is(
  (select backoff_until from public.sources where id = '30000000-0000-0000-0000-000000000041'),
  '2026-11-01T01:05:01Z'::timestamptz,
  'the first failure creates a five-minute backoff'
);

insert into public.source_checks (
  source_id,
  started_at,
  completed_at,
  outcome
)
values (
  '30000000-0000-0000-0000-000000000041',
  '2026-11-01T01:10:00Z',
  '2026-11-01T01:10:01Z',
  'successful'
);

select is(
  (select consecutive_failures from public.sources where id = '30000000-0000-0000-0000-000000000041'),
  0,
  'a successful source check resets the retry counter'
);
select ok(
  (select backoff_until is null from public.sources where id = '30000000-0000-0000-0000-000000000041'),
  'a successful source check clears backoff'
);

select ok(
  public.get_automation_targets() -> 'source_ids'
    @> '["30000000-0000-0000-0000-000000000041"]'::jsonb,
  'automation selects an active due source'
);
select ok(
  public.get_automation_targets() -> 'user_ids'
    @> '["10000000-0000-0000-0000-000000000041"]'::jsonb,
  'automation selects the owner for matching'
);

insert into public.jobs (
  id,
  company_id,
  source_id,
  external_job_id,
  dedupe_key,
  title,
  normalized_title,
  location,
  workplace_type,
  employment_type,
  apply_url,
  canonical_apply_url,
  first_seen_at,
  last_seen_at,
  last_verified_at,
  content_hash
)
values
  (
    '40000000-0000-0000-0000-000000000041',
    '20000000-0000-0000-0000-000000000041',
    '30000000-0000-0000-0000-000000000041',
    'automation-one',
    'external:automation-one',
    'Software Engineer, New Grad',
    'software engineer, new grad',
    'Remote',
    'remote',
    'full-time',
    'https://automation.example.test/jobs/one',
    'https://automation.example.test/jobs/one',
    '2026-11-01T02:00:00Z',
    '2026-11-01T02:00:00Z',
    '2026-11-01T02:00:00Z',
    'automation-one-hash'
  ),
  (
    '40000000-0000-0000-0000-000000000042',
    '20000000-0000-0000-0000-000000000041',
    '30000000-0000-0000-0000-000000000041',
    'automation-two',
    'external:automation-two',
    'Associate Software Engineer',
    'associate software engineer',
    'Seattle, WA',
    'hybrid',
    'full-time',
    'https://automation.example.test/jobs/two',
    'https://automation.example.test/jobs/two',
    '2026-11-01T02:05:00Z',
    '2026-11-01T02:05:00Z',
    '2026-11-01T02:05:00Z',
    'automation-two-hash'
  );

insert into public.job_matches (
  user_id,
  preference_id,
  job_id,
  status,
  career_level,
  sponsorship_status,
  match_reasons,
  preference_updated_at,
  job_content_hash,
  matcher_version
)
select
  '10000000-0000-0000-0000-000000000041',
  '50000000-0000-0000-0000-000000000041',
  job.id,
  'matched',
  'new_grad',
  'unknown',
  '[{"code":"title_match","message":"Title matches.","evidence":["software engineer"]}]',
  preference.updated_at,
  job.content_hash,
  'deterministic-v1'
from public.jobs as job
cross join public.user_preferences as preference
where job.id in (
    '40000000-0000-0000-0000-000000000041',
    '40000000-0000-0000-0000-000000000042'
  )
  and preference.user_id = '10000000-0000-0000-0000-000000000041';

select is(
  public.queue_match_notifications('10000000-0000-0000-0000-000000000041') ->> 'queued',
  '2',
  'matching jobs create two durable notification items'
);
select is(
  public.queue_match_notifications('10000000-0000-0000-0000-000000000041') ->> 'queued',
  '0',
  'queueing the same matches is idempotent'
);
select is(
  (select count(*) from public.notifications where user_id = '10000000-0000-0000-0000-000000000041'),
  2::bigint,
  'the queue contains no duplicate notification rows'
);

create temporary table claimed_delivery as
select public.claim_notification_delivery(50, 15) as payload;

select is(
  (select jsonb_array_length(payload -> 'payload') from claimed_delivery),
  2,
  'due items for one user are grouped into one digest'
);
select is(
  (select payload ->> 'recipient_email' from claimed_delivery),
  'alerts@launchpad.test',
  'the delivery uses the authenticated account email'
);
select is(
  (select payload ->> 'attempt_count' from claimed_delivery),
  '1',
  'claiming records the first attempt'
);
select ok(
  public.claim_notification_delivery(50, 15) is null,
  'an active lease prevents a concurrent duplicate claim'
);

select is(
  public.complete_notification_delivery(
    (select (payload ->> 'id')::uuid from claimed_delivery),
    false,
    null,
    'Provider unavailable',
    5
  ) ->> 'status',
  'pending',
  'a transient provider failure schedules a retry'
);
select is(
  (select status::text from public.notifications where user_id = '10000000-0000-0000-0000-000000000041' limit 1),
  'pending',
  'notification items remain pending during retry backoff'
);

update public.notification_deliveries
set next_attempt_at = now() - interval '1 minute'
where id = (select (payload ->> 'id')::uuid from claimed_delivery);

create temporary table retried_delivery as
select public.claim_notification_delivery(50, 15) as payload;

select is(
  (select payload ->> 'dedupe_key' from retried_delivery),
  (select payload ->> 'dedupe_key' from claimed_delivery),
  'a retry reuses the provider idempotency key'
);
select is(
  (select payload -> 'payload' from retried_delivery),
  (select payload -> 'payload' from claimed_delivery),
  'a retry reuses the immutable email payload'
);
select is(
  (select payload ->> 'attempt_count' from retried_delivery),
  '2',
  'retry attempts are counted'
);
select is(
  public.complete_notification_delivery(
    (select (payload ->> 'id')::uuid from retried_delivery),
    true,
    'resend-message-123',
    null,
    5
  ) ->> 'status',
  'sent',
  'a successful provider response completes the delivery'
);
select is(
  (select count(*) from public.notifications where user_id = '10000000-0000-0000-0000-000000000041' and status = 'sent'),
  2::bigint,
  'every item in the digest is marked sent atomically'
);
select is(
  (select count(distinct provider_message_id) from public.notifications where user_id = '10000000-0000-0000-0000-000000000041'),
  1::bigint,
  'the digest records one provider message id'
);
select is(
  public.complete_notification_delivery(
    (select (payload ->> 'id')::uuid from retried_delivery),
    true,
    'resend-message-123',
    null,
    5
  ) ->> 'status',
  'sent',
  'completing an already sent delivery is idempotent'
);

select ok(
  not has_function_privilege('anon', 'public.get_automation_targets()', 'execute'),
  'anonymous clients cannot enumerate automation targets'
);
select ok(
  not has_function_privilege('authenticated', 'public.queue_match_notifications(uuid)', 'execute'),
  'browser clients cannot create notification queue items'
);
select ok(
  not has_table_privilege('authenticated', 'public.notification_deliveries', 'select'),
  'browser clients cannot read delivery recipient data'
);

select * from finish();
rollback;
