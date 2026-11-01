begin;

create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;

select plan(23);

insert into auth.users (id)
values
  ('10000000-0000-0000-0000-000000000031'),
  ('10000000-0000-0000-0000-000000000032');

select set_config('request.jwt.claim.sub', '10000000-0000-0000-0000-000000000031', true);
set local role authenticated;

select lives_ok(
  $$ select public.create_watchlist_company(
    'Launchpad Test Company',
    'https://example.test/careers',
    'https://boards-api.greenhouse.io/v1/boards/launchpad-test/jobs/',
    30
  ) $$,
  'an authenticated user can atomically add a supported source'
);
select is(
  (select count(*) from public.companies where name = 'Launchpad Test Company'),
  1::bigint,
  'the company is created once'
);
select is(
  (select source.source_url from public.sources as source join public.companies as company on company.id = source.company_id where company.name = 'Launchpad Test Company'),
  'https://boards-api.greenhouse.io/v1/boards/launchpad-test/jobs',
  'the source URL is normalized'
);
select is(
  (select source.check_interval_minutes from public.sources as source join public.companies as company on company.id = source.company_id where company.name = 'Launchpad Test Company'),
  30,
  'the selected monitoring interval is stored'
);
select throws_ok(
  $$ select public.create_watchlist_company(
    'Unsupported Source',
    'https://example.test/careers',
    'https://jobs.example.test/feed',
    60
  ) $$,
  '22023',
  'source URL must be an official Greenhouse list-jobs endpoint',
  'unsupported sources are rejected'
);
select is(
  (select count(*) from public.companies where name = 'Unsupported Source'),
  0::bigint,
  'a rejected source leaves no partial company'
);
select throws_ok(
  $$ select public.create_watchlist_company(
    'Bad Cadence',
    'https://example.test/careers',
    'https://boards-api.greenhouse.io/v1/boards/bad-cadence/jobs',
    17
  ) $$,
  '22023',
  'unsupported check interval',
  'unsupported monitoring intervals are rejected'
);

select lives_ok(
  $$ select public.set_company_monitoring(
    (select id from public.companies where name = 'Launchpad Test Company'),
    false
  ) $$,
  'an owner can pause company monitoring'
);
select is(
  (select is_active from public.companies where name = 'Launchpad Test Company'),
  false,
  'pausing disables the company'
);
select is(
  (select source.is_active from public.sources as source join public.companies as company on company.id = source.company_id where company.name = 'Launchpad Test Company'),
  false,
  'pausing disables its sources in the same operation'
);

select lives_ok(
  $$ select public.update_job_preferences(
    '["software engineer", "backend engineer"]',
    '["new_grad", "entry_level"]',
    '["full-time"]',
    '["Seattle, WA", "Remote"]',
    '["remote", "hybrid"]',
    'any',
    '["distributed systems"]',
    '["staff"]',
    false,
    'hourly_digest'
  ) $$,
  'an owner can update explicit job preferences'
);
select is(
  (select target_titles from public.user_preferences where user_id = auth.uid()),
  '["software engineer", "backend engineer"]'::jsonb,
  'target titles are stored as structured values'
);
select is(
  (select alert_frequency::text from public.user_preferences where user_id = auth.uid()),
  'hourly_digest',
  'alert frequency is stored'
);
select throws_ok(
  $$ select public.update_job_preferences(
    '[]',
    '["senior"]',
    '["full-time"]',
    '[]',
    '[]',
    'any',
    '[]',
    '[]',
    false,
    'immediate'
  ) $$,
  '23514',
  null,
  'invalid career levels are rejected by database constraints'
);

reset role;

create temporary table watchlist_target as
select id from public.companies where name = 'Launchpad Test Company';
grant select on watchlist_target to authenticated;

select set_config('request.jwt.claim.sub', '10000000-0000-0000-0000-000000000032', true);
set local role authenticated;

select throws_ok(
  $$ select public.set_company_monitoring(
    (select id from watchlist_target),
    true
  ) $$,
  '42501',
  'company is not visible to the authenticated user',
  'another user cannot change monitoring state'
);

reset role;
select ok(
  not has_function_privilege(
    'anon',
    'public.create_watchlist_company(text,text,text,integer)',
    'execute'
  ),
  'anonymous clients cannot add watchlist entries'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.set_company_monitoring(uuid,boolean)',
    'execute'
  ),
  'anonymous clients cannot pause monitoring'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.update_job_preferences(jsonb,jsonb,jsonb,jsonb,jsonb,text,jsonb,jsonb,boolean,public.alert_frequency)',
    'execute'
  ),
  'anonymous clients cannot update preferences'
);
select ok(
  not has_table_privilege('authenticated', 'public.companies', 'insert'),
  'authenticated clients cannot bypass atomic company creation'
);
select ok(
  not has_table_privilege('authenticated', 'public.sources', 'update'),
  'authenticated clients cannot bypass source monitoring rules'
);
select ok(
  not has_table_privilege('authenticated', 'public.user_preferences', 'update'),
  'authenticated clients cannot bypass preference invalidation'
);
select is(
  (select count(*) from public.companies where name = 'Launchpad Test Company'),
  1::bigint,
  'cross-owner attempts leave the company intact'
);
select is(
  (select count(*) from public.sources where company_id = (select id from watchlist_target)),
  1::bigint,
  'the watchlist keeps exactly one supported source'
);

select * from finish();
rollback;
