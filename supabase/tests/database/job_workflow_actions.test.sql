begin;

create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;

select plan(19);

insert into auth.users (id)
values
  ('10000000-0000-0000-0000-000000000021'),
  ('10000000-0000-0000-0000-000000000022');

insert into public.companies (id, owner_id, name, careers_url)
values
  (
    '20000000-0000-0000-0000-000000000021',
    '10000000-0000-0000-0000-000000000021',
    'Workflow Owner Company',
    'https://workflow-owner.example.test/careers'
  ),
  (
    '20000000-0000-0000-0000-000000000022',
    '10000000-0000-0000-0000-000000000022',
    'Workflow Other Company',
    'https://workflow-other.example.test/careers'
  );

insert into public.sources (id, company_id, source_type, source_url)
values
  (
    '30000000-0000-0000-0000-000000000021',
    '20000000-0000-0000-0000-000000000021',
    'greenhouse',
    'https://boards-api.greenhouse.io/v1/boards/workflow-owner/jobs'
  ),
  (
    '30000000-0000-0000-0000-000000000022',
    '20000000-0000-0000-0000-000000000022',
    'greenhouse',
    'https://boards-api.greenhouse.io/v1/boards/workflow-other/jobs'
  );

insert into public.jobs (
  id,
  company_id,
  source_id,
  external_job_id,
  dedupe_key,
  title,
  normalized_title,
  apply_url,
  canonical_apply_url,
  first_seen_at,
  last_seen_at,
  last_verified_at,
  content_hash
)
values
  (
    '40000000-0000-0000-0000-000000000021',
    '20000000-0000-0000-0000-000000000021',
    '30000000-0000-0000-0000-000000000021',
    'workflow-owner-one',
    'external:workflow-owner-one',
    'Software Engineer, New Grad',
    'software engineer, new grad',
    'https://workflow-owner.example.test/jobs/one',
    'https://workflow-owner.example.test/jobs/one',
    '2026-10-31T10:00:00Z',
    '2026-10-31T10:00:00Z',
    '2026-10-31T10:00:00Z',
    'workflow-owner-one-hash'
  ),
  (
    '40000000-0000-0000-0000-000000000022',
    '20000000-0000-0000-0000-000000000021',
    '30000000-0000-0000-0000-000000000021',
    'workflow-owner-two',
    'external:workflow-owner-two',
    'Associate Software Engineer',
    'associate software engineer',
    'https://workflow-owner.example.test/jobs/two',
    'https://workflow-owner.example.test/jobs/two',
    '2026-10-31T11:00:00Z',
    '2026-10-31T11:00:00Z',
    '2026-10-31T11:00:00Z',
    'workflow-owner-two-hash'
  ),
  (
    '40000000-0000-0000-0000-000000000023',
    '20000000-0000-0000-0000-000000000022',
    '30000000-0000-0000-0000-000000000022',
    'workflow-other',
    'external:workflow-other',
    'Software Engineer I',
    'software engineer i',
    'https://workflow-other.example.test/jobs/one',
    'https://workflow-other.example.test/jobs/one',
    '2026-10-31T12:00:00Z',
    '2026-10-31T12:00:00Z',
    '2026-10-31T12:00:00Z',
    'workflow-other-hash'
  );

select set_config('request.jwt.claim.sub', '10000000-0000-0000-0000-000000000021', true);
set local role authenticated;

select lives_ok(
  $$ select public.set_job_workflow_status('40000000-0000-0000-0000-000000000021', 'saved') $$,
  'an owner can save a visible job'
);
select is(
  (select application_status::text from public.user_jobs where job_id = '40000000-0000-0000-0000-000000000021'),
  'saved',
  'saving records the saved status'
);
select ok(
  (select saved_at is not null from public.user_jobs where job_id = '40000000-0000-0000-0000-000000000021'),
  'saving records saved_at'
);
select ok(
  (select applied_at is null from public.user_jobs where job_id = '40000000-0000-0000-0000-000000000021'),
  'saving does not invent an application time'
);

select lives_ok(
  $$ select public.set_job_workflow_status('40000000-0000-0000-0000-000000000021', 'new') $$,
  'a saved job can be unsaved'
);
select is(
  (select application_status::text from public.user_jobs where job_id = '40000000-0000-0000-0000-000000000021'),
  'new',
  'unsaving restores the new status'
);
select ok(
  (select saved_at is null from public.user_jobs where job_id = '40000000-0000-0000-0000-000000000021'),
  'unsaving clears saved_at'
);

select lives_ok(
  $$ select public.set_job_workflow_status('40000000-0000-0000-0000-000000000021', 'applied') $$,
  'an owner can mark a job applied'
);
select is(
  (select application_status::text from public.user_jobs where job_id = '40000000-0000-0000-0000-000000000021'),
  'applied',
  'applying records the applied status'
);
select ok(
  (select applied_at is not null from public.user_jobs where job_id = '40000000-0000-0000-0000-000000000021'),
  'applying records applied_at'
);

create temporary table applied_snapshot as
select applied_at
from public.user_jobs
where job_id = '40000000-0000-0000-0000-000000000021';

select lives_ok(
  $$ select public.set_job_workflow_status('40000000-0000-0000-0000-000000000021', 'applied') $$,
  'repeating applied is idempotent'
);
select is(
  (select applied_at from public.user_jobs where job_id = '40000000-0000-0000-0000-000000000021'),
  (select applied_at from applied_snapshot),
  'an applied retry preserves the original applied_at'
);
select throws_ok(
  $$ select public.set_job_workflow_status('40000000-0000-0000-0000-000000000021', 'saved') $$,
  '22023',
  'workflow status cannot move from applied to saved',
  'a stale save cannot regress an applied job'
);

select lives_ok(
  $$ select public.set_job_workflow_status('40000000-0000-0000-0000-000000000022', 'not_interested') $$,
  'an owner can dismiss a visible job'
);
select is(
  (select application_status::text from public.user_jobs where job_id = '40000000-0000-0000-0000-000000000022'),
  'not_interested',
  'dismissing records not_interested'
);
select ok(
  (select saved_at is null from public.user_jobs where job_id = '40000000-0000-0000-0000-000000000022'),
  'dismissed jobs are not counted as saved'
);

select throws_ok(
  $$ select public.set_job_workflow_status('40000000-0000-0000-0000-000000000023', 'saved') $$,
  '42501',
  'job is not visible to the authenticated user',
  'an owner cannot mutate another user''s job'
);

reset role;

select is(
  (select count(*) from public.user_jobs where job_id = '40000000-0000-0000-0000-000000000023'),
  0::bigint,
  'a rejected cross-owner mutation creates no interaction'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.set_job_workflow_status(uuid, public.application_status)',
    'execute'
  ),
  'anonymous clients cannot call the workflow mutation'
);

select * from finish();
rollback;
