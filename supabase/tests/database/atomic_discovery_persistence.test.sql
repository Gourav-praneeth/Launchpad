begin;

create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;

select plan(15);

insert into auth.users (id)
values ('10000000-0000-0000-0000-000000000001');

insert into public.companies (id, owner_id, name, careers_url)
values (
  '20000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  'Launchpad Fixture',
  'https://careers.example.test'
);

insert into public.sources (id, company_id, source_type, source_url)
values (
  '30000000-0000-0000-0000-000000000001',
  '20000000-0000-0000-0000-000000000001',
  'greenhouse',
  'https://boards-api.greenhouse.io/v1/boards/launchpad-fixture/jobs'
);

create temporary table persistence_results (
  label text primary key,
  result jsonb not null
);

insert into persistence_results
select 'first', public.persist_discovery_check(
  '30000000-0000-0000-0000-000000000001',
  '2026-10-30T10:00:00Z',
  '2026-10-30T10:00:05Z',
  'successful',
  '[{
    "external_job_id": "127817",
    "dedupe_key": "external:127817",
    "title": "Software Engineer, New Grad",
    "normalized_title": "software engineer, new grad",
    "location": "San Francisco, CA",
    "workplace_type": null,
    "employment_type": null,
    "description": "Build dependable systems.",
    "apply_url": "https://careers.example.test/jobs?gh_jid=127817",
    "canonical_apply_url": "https://careers.example.test/jobs?gh_jid=127817",
    "employer_posted_at": null,
    "source_updated_at": "2026-10-29T23:45:12Z",
    "content_hash": "hash-v1"
  }]'::jsonb,
  1,
  null,
  null,
  200
);

insert into persistence_results
select 'repeat', public.persist_discovery_check(
  '30000000-0000-0000-0000-000000000001',
  '2026-10-30T10:05:00Z',
  '2026-10-30T10:05:05Z',
  'successful',
  '[{
    "external_job_id": "127817",
    "dedupe_key": "external:127817",
    "title": "Software Engineer, New Grad",
    "normalized_title": "software engineer, new grad",
    "location": "San Francisco, CA",
    "workplace_type": null,
    "employment_type": null,
    "description": "Build dependable systems.",
    "apply_url": "https://careers.example.test/jobs?gh_jid=127817",
    "canonical_apply_url": "https://careers.example.test/jobs?gh_jid=127817",
    "employer_posted_at": null,
    "source_updated_at": "2026-10-29T23:45:12Z",
    "content_hash": "hash-v1"
  }]'::jsonb,
  1,
  null,
  null,
  200
);

insert into persistence_results
select 'failure', public.persist_discovery_check(
  '30000000-0000-0000-0000-000000000001',
  '2026-10-30T10:10:00Z',
  '2026-10-30T10:10:05Z',
  'failed',
  '[]'::jsonb,
  0,
  'request_failed',
  'Greenhouse request failed: ReadTimeout',
  null
);

select is(
  (select result ->> 'inserted' from persistence_results where label = 'first'),
  '1',
  'first discovery inserts one job'
);
select is(
  (select result ->> 'unchanged' from persistence_results where label = 'repeat'),
  '1',
  'repeat discovery is unchanged'
);
select is((select count(*) from public.jobs), 1::bigint, 'repeat discovery is deduplicated');
select is(
  (select first_seen_at from public.jobs),
  '2026-10-30T10:00:05Z'::timestamptz,
  'first_seen_at remains the initial observation'
);
select is(
  (select last_seen_at from public.jobs),
  '2026-10-30T10:05:05Z'::timestamptz,
  'failed checks do not advance last_seen_at'
);
select is((select status::text from public.jobs), 'open', 'failed checks do not close jobs');
select is(
  (select count(*) from public.job_events where event_type = 'first_seen'),
  1::bigint,
  'first_seen event is idempotent'
);
select is(
  (select outcome::text from public.source_checks order by completed_at desc limit 1),
  'failed',
  'failed source check is audited'
);

update public.jobs set status = 'closed';

insert into persistence_results
select 'changed', public.persist_discovery_check(
  '30000000-0000-0000-0000-000000000001',
  '2026-10-30T10:15:00Z',
  '2026-10-30T10:15:05Z',
  'successful',
  '[{
    "external_job_id": "127817",
    "dedupe_key": "external:127817",
    "title": "Software Engineer I, New Grad",
    "normalized_title": "software engineer i, new grad",
    "location": "San Francisco, CA",
    "workplace_type": null,
    "employment_type": null,
    "description": "Build dependable distributed systems.",
    "apply_url": "https://careers.example.test/jobs?gh_jid=127817",
    "canonical_apply_url": "https://careers.example.test/jobs?gh_jid=127817",
    "employer_posted_at": null,
    "source_updated_at": "2026-10-30T10:14:00Z",
    "content_hash": "hash-v2"
  }]'::jsonb,
  1,
  null,
  null,
  200
);

select is(
  (select result ->> 'updated' from persistence_results where label = 'changed'),
  '1',
  'meaningful content change is counted'
);
select is(
  (select result ->> 'reopened' from persistence_results where label = 'changed'),
  '1',
  'positive observation reopens a closed job'
);
select is(
  (select first_seen_at from public.jobs),
  '2026-10-30T10:00:05Z'::timestamptz,
  'updates never reset first_seen_at'
);
select is((select status::text from public.jobs), 'open', 'reobserved job is open');
select is(
  (select count(*) from public.job_events where event_type = 'updated'),
  1::bigint,
  'meaningful change creates one updated event'
);
select is(
  (select count(*) from public.job_events where event_type = 'reopened'),
  1::bigint,
  'reopening creates one reopened event'
);
select is(
  (select count(*) from public.source_checks),
  4::bigint,
  'every discovery outcome creates an audit record'
);

select * from finish();
rollback;
