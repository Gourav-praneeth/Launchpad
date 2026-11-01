begin;

create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;

select plan(21);

insert into auth.users (id)
values
  ('10000000-0000-0000-0000-000000000011'),
  ('10000000-0000-0000-0000-000000000012');

select is(
  (
    select count(*)
    from public.user_preferences
    where user_id = '10000000-0000-0000-0000-000000000011'
  ),
  1::bigint,
  'creating an auth user creates one default preference row'
);

select is(
  (
    select career_levels
    from public.user_preferences
    where user_id = '10000000-0000-0000-0000-000000000011'
  ),
  '["new_grad", "entry_level", "early_career"]'::jsonb,
  'onboarding preferences use the new-grad career-level defaults'
);

insert into public.companies (id, owner_id, name, careers_url)
values
  (
    '20000000-0000-0000-0000-000000000011',
    '10000000-0000-0000-0000-000000000011',
    'Matching Owner Company',
    'https://owner.example.test/careers'
  ),
  (
    '20000000-0000-0000-0000-000000000012',
    '10000000-0000-0000-0000-000000000012',
    'Other Matching Company',
    'https://other.example.test/careers'
  );

insert into public.sources (id, company_id, source_type, source_url)
values
  (
    '30000000-0000-0000-0000-000000000011',
    '20000000-0000-0000-0000-000000000011',
    'greenhouse',
    'https://boards-api.greenhouse.io/v1/boards/matching-owner/jobs'
  ),
  (
    '30000000-0000-0000-0000-000000000012',
    '20000000-0000-0000-0000-000000000012',
    'greenhouse',
    'https://boards-api.greenhouse.io/v1/boards/matching-other/jobs'
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
  description,
  apply_url,
  canonical_apply_url,
  first_seen_at,
  last_seen_at,
  last_verified_at,
  status,
  content_hash
)
values
  (
    '40000000-0000-0000-0000-000000000011',
    '20000000-0000-0000-0000-000000000011',
    '30000000-0000-0000-0000-000000000011',
    'owner-open',
    'external:owner-open',
    'Software Engineer, New Grad',
    'software engineer, new grad',
    'San Francisco, CA',
    'hybrid',
    'full-time',
    'Build dependable systems.',
    'https://owner.example.test/jobs/open',
    'https://owner.example.test/jobs/open',
    '2026-10-30T10:00:00Z',
    '2026-10-30T10:00:00Z',
    '2026-10-30T10:00:00Z',
    'open',
    'owner-open-hash'
  ),
  (
    '40000000-0000-0000-0000-000000000012',
    '20000000-0000-0000-0000-000000000011',
    '30000000-0000-0000-0000-000000000011',
    'owner-closed',
    'external:owner-closed',
    'Software Engineer, New Grad',
    'software engineer, new grad',
    'New York, NY',
    'remote',
    'full-time',
    'Build dependable systems.',
    'https://owner.example.test/jobs/closed',
    'https://owner.example.test/jobs/closed',
    '2026-10-30T10:00:00Z',
    '2026-10-30T10:00:00Z',
    '2026-10-30T10:00:00Z',
    'closed',
    'owner-closed-hash'
  ),
  (
    '40000000-0000-0000-0000-000000000013',
    '20000000-0000-0000-0000-000000000012',
    '30000000-0000-0000-0000-000000000012',
    'other-open',
    'external:other-open',
    'Software Engineer, New Grad',
    'software engineer, new grad',
    'Austin, TX',
    'on-site',
    'full-time',
    'Build dependable systems.',
    'https://other.example.test/jobs/open',
    'https://other.example.test/jobs/open',
    '2026-10-30T10:00:00Z',
    '2026-10-30T10:00:00Z',
    '2026-10-30T10:00:00Z',
    'open',
    'other-open-hash'
  );

update public.user_preferences
set id = '50000000-0000-0000-0000-000000000011',
    locations = '["San Francisco"]'::jsonb,
    workplace_types = '["hybrid"]'::jsonb
where user_id = '10000000-0000-0000-0000-000000000011';

select is(
  (
    select career_levels
    from public.user_preferences
    where id = '50000000-0000-0000-0000-000000000011'
  ),
  '["new_grad", "entry_level", "early_career"]'::jsonb,
  'preferences receive the new-grad career-level defaults'
);

select is(
  (
    select sponsorship_preference
    from public.user_preferences
    where id = '50000000-0000-0000-0000-000000000011'
  ),
  'any',
  'preferences receive an explicit sponsorship default'
);

select is(
  jsonb_array_length(
    public.get_matching_context('10000000-0000-0000-0000-000000000011') -> 'jobs'
  ),
  1,
  'matching context includes only the owner open-job snapshot'
);

select is(
  public.get_matching_context('10000000-0000-0000-0000-000000000011')
    -> 'jobs' -> 0 ->> 'id',
  '40000000-0000-0000-0000-000000000011',
  'matching context identifies the expected open job'
);

select is(
  public.get_matching_context('10000000-0000-0000-0000-000000000011')
    -> 'preference' ->> 'include_senior_roles',
  'false',
  'matching context carries the senior-role preference'
);

create temporary table matching_results as
select public.persist_job_match_results(
  '10000000-0000-0000-0000-000000000011',
  (
    select updated_at
    from public.user_preferences
    where id = '50000000-0000-0000-0000-000000000011'
  ),
  'deterministic-v1',
  '[{
    "job_id": "40000000-0000-0000-0000-000000000011",
    "job_content_hash": "owner-open-hash",
    "status": "matched",
    "career_level": "new_grad",
    "sponsorship_status": "unknown",
    "match_reasons": [{"code": "title_match", "message": "Title matches.", "evidence": ["software engineer"]}],
    "review_reasons": [],
    "rejection_reasons": []
  }]'::jsonb
) as result;

select is(
  (select result ->> 'evaluated' from matching_results),
  '1',
  'the batch transaction evaluates the complete snapshot'
);
select is(
  (select result ->> 'matched' from matching_results),
  '1',
  'the batch transaction returns matched counts'
);
select is((select count(*) from public.job_matches where user_id = '10000000-0000-0000-0000-000000000011'), 1::bigint, 'one result is stored');
select is(
  (select status::text from public.job_matches where user_id = '10000000-0000-0000-0000-000000000011'),
  'matched',
  'the explainable result status is stored'
);
select is(
  (select match_reasons -> 0 ->> 'code' from public.job_matches where user_id = '10000000-0000-0000-0000-000000000011'),
  'title_match',
  'stable reason codes are stored'
);
select is(
  (select matcher_version from public.job_matches where user_id = '10000000-0000-0000-0000-000000000011'),
  'deterministic-v1',
  'the matcher version is stored'
);

select throws_ok(
  $$
    select public.persist_job_match_results(
      '10000000-0000-0000-0000-000000000011',
      '2020-01-01T00:00:00Z',
      'deterministic-v1',
      '[]'::jsonb
    )
  $$,
  'P0001',
  'user preferences changed during matching',
  'stale preference snapshots are rejected'
);

select throws_ok(
  $$
    select public.persist_job_match_results(
      '10000000-0000-0000-0000-000000000011',
      (
        select updated_at
        from public.user_preferences
        where id = '50000000-0000-0000-0000-000000000011'
      ),
      'deterministic-v1',
      '[]'::jsonb
    )
  $$,
  'P0001',
  'match results do not cover the current open-job snapshot',
  'incomplete result batches are rejected'
);

select throws_ok(
  $$
    select public.persist_job_match_results(
      '10000000-0000-0000-0000-000000000011',
      (
        select updated_at
        from public.user_preferences
        where id = '50000000-0000-0000-0000-000000000011'
      ),
      'deterministic-v1',
      '[{
        "job_id": "40000000-0000-0000-0000-000000000011",
        "job_content_hash": "stale-hash",
        "status": "matched",
        "career_level": "new_grad",
        "sponsorship_status": "unknown",
        "match_reasons": [],
        "review_reasons": [],
        "rejection_reasons": []
      }]'::jsonb
    )
  $$,
  'P0001',
  'job changed during matching',
  'stale job snapshots are rejected'
);

select ok(
  not has_function_privilege(
    'authenticated',
    'public.get_matching_context(uuid)',
    'execute'
  ),
  'authenticated clients cannot call the matching context RPC'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.get_matching_context(uuid)',
    'execute'
  ),
  'the service role can call the matching context RPC'
);
select ok(
  not has_table_privilege('authenticated', 'public.job_matches', 'insert'),
  'authenticated clients cannot write derived match results'
);

set local role authenticated;
select set_config(
  'request.jwt.claim.sub',
  '10000000-0000-0000-0000-000000000011',
  true
);
select is(
  (select count(*) from public.job_matches),
  1::bigint,
  'an authenticated owner can read their result'
);
select set_config(
  'request.jwt.claim.sub',
  '10000000-0000-0000-0000-000000000012',
  true
);
select is(
  (select count(*) from public.job_matches),
  0::bigint,
  'another authenticated user cannot read the result'
);
reset role;

select * from finish();
rollback;
