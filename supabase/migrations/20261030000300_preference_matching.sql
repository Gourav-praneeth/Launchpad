create type public.job_match_status as enum ('matched', 'review', 'rejected');

create function public.is_nonempty_text_array(input jsonb)
returns boolean
language sql
immutable
set search_path = ''
as $$
  select jsonb_typeof(input) = 'array'
    and not exists (
      select 1
      from jsonb_array_elements(input) as item(value)
      where jsonb_typeof(item.value) <> 'string'
        or length(trim(item.value #>> '{}')) = 0
    );
$$;

grant execute on function public.is_nonempty_text_array(jsonb) to authenticated, service_role;

update public.user_preferences
set career_levels = '["new_grad", "entry_level", "early_career"]'::jsonb
where career_levels = '[]'::jsonb;

update public.user_preferences
set sponsorship_preference = 'any'
where sponsorship_preference is null;

alter table public.user_preferences
  alter column career_levels
    set default '["new_grad", "entry_level", "early_career"]'::jsonb,
  alter column sponsorship_preference set default 'any',
  alter column sponsorship_preference set not null,
  add column include_senior_roles boolean not null default false,
  add constraint user_preferences_text_arrays_valid check (
    public.is_nonempty_text_array(target_titles)
    and public.is_nonempty_text_array(career_levels)
    and public.is_nonempty_text_array(employment_types)
    and public.is_nonempty_text_array(locations)
    and public.is_nonempty_text_array(workplace_types)
    and public.is_nonempty_text_array(include_keywords)
    and public.is_nonempty_text_array(exclude_keywords)
  ),
  add constraint user_preferences_career_levels_valid check (
    jsonb_array_length(career_levels) > 0
    and career_levels <@ '["new_grad", "entry_level", "early_career", "experienced"]'::jsonb
  ),
  add constraint user_preferences_employment_types_valid check (
    employment_types <@ '["full-time", "part-time", "internship", "contract", "temporary"]'::jsonb
  ),
  add constraint user_preferences_workplace_types_valid check (
    workplace_types <@ '["remote", "hybrid", "on-site"]'::jsonb
  );

alter table public.user_preferences
  add constraint user_preferences_id_user_unique unique (id, user_id);

update public.jobs
set content_hash = encode(
  extensions.digest(
    concat_ws(
      '|',
      title,
      coalesce(location, ''),
      coalesce(workplace_type, ''),
      coalesce(employment_type, ''),
      coalesce(description, ''),
      apply_url,
      canonical_apply_url,
      coalesce(employer_posted_at::text, '')
    ),
    'sha256'
  ),
  'hex'
)
where content_hash is null;

alter table public.jobs alter column content_hash set not null;

create table public.job_matches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  preference_id uuid not null,
  job_id uuid not null references public.jobs(id) on delete cascade,
  status public.job_match_status not null,
  career_level text not null check (
    career_level in ('new_grad', 'entry_level', 'early_career', 'experienced', 'unknown')
  ),
  sponsorship_status text not null check (
    sponsorship_status in ('available', 'unavailable', 'unknown')
  ),
  match_reasons jsonb not null default '[]'::jsonb,
  review_reasons jsonb not null default '[]'::jsonb,
  rejection_reasons jsonb not null default '[]'::jsonb,
  preference_updated_at timestamptz not null,
  job_content_hash text not null check (length(job_content_hash) > 0),
  matcher_version text not null check (length(trim(matcher_version)) > 0),
  evaluated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint job_matches_preference_owner_fk
    foreign key (preference_id, user_id)
    references public.user_preferences(id, user_id)
    on delete cascade,
  constraint job_matches_user_job_unique unique (user_id, job_id),
  constraint job_matches_reason_arrays check (
    jsonb_typeof(match_reasons) = 'array'
    and jsonb_typeof(review_reasons) = 'array'
    and jsonb_typeof(rejection_reasons) = 'array'
  )
);

create index job_matches_user_status_idx
  on public.job_matches (user_id, status, evaluated_at desc);
create index job_matches_job_id_idx on public.job_matches (job_id);

create trigger job_matches_set_updated_at
before update on public.job_matches
for each row execute function public.set_updated_at();

alter table public.job_matches enable row level security;

create policy job_matches_owner_select on public.job_matches
for select to authenticated
using (user_id = auth.uid() and public.owns_job(job_id));

revoke insert, update, delete on public.job_matches from authenticated, anon;
grant select on public.job_matches to authenticated;
grant all on public.job_matches to service_role;

create function public.get_matching_context(p_user_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_preference public.user_preferences%rowtype;
  v_jobs jsonb;
begin
  select preference.*
  into v_preference
  from public.user_preferences as preference
  where preference.user_id = p_user_id;

  if v_preference.id is null then
    raise exception 'user preferences do not exist';
  end if;

  select coalesce(jsonb_agg(candidate.payload order by candidate.job_id), '[]'::jsonb)
  into v_jobs
  from (
    select
      job.id as job_id,
      jsonb_build_object(
        'id', job.id,
        'external_job_id', job.external_job_id,
        'dedupe_key', job.dedupe_key,
        'title', job.title,
        'location', job.location,
        'workplace_type', job.workplace_type,
        'employment_type', job.employment_type,
        'description', job.description,
        'apply_url', job.apply_url,
        'canonical_apply_url', job.canonical_apply_url,
        'employer_posted_at', job.employer_posted_at,
        'source_updated_at', job.source_updated_at,
        'content_hash', job.content_hash
      ) as payload
    from public.jobs as job
    join public.companies as company on company.id = job.company_id
    where company.owner_id = p_user_id
      and job.status = 'open'
  ) as candidate;

  return jsonb_build_object(
    'preference', jsonb_build_object(
      'id', v_preference.id,
      'updated_at', v_preference.updated_at,
      'target_titles', v_preference.target_titles,
      'career_levels', v_preference.career_levels,
      'employment_types', v_preference.employment_types,
      'locations', v_preference.locations,
      'workplace_types', v_preference.workplace_types,
      'include_keywords', v_preference.include_keywords,
      'exclude_keywords', v_preference.exclude_keywords,
      'sponsorship_preference', v_preference.sponsorship_preference,
      'include_senior_roles', v_preference.include_senior_roles
    ),
    'jobs', v_jobs
  );
end;
$$;

create function public.persist_job_match_results(
  p_user_id uuid,
  p_preference_updated_at timestamptz,
  p_matcher_version text,
  p_results jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_preference_id uuid;
  v_current_preference_updated_at timestamptz;
  v_result jsonb;
  v_job_id uuid;
  v_job_content_hash text;
  v_current_job_content_hash text;
  v_expected_count integer;
  v_result_count integer;
  v_matched integer := 0;
  v_review integer := 0;
  v_rejected integer := 0;
begin
  if p_matcher_version is null or length(trim(p_matcher_version)) = 0 then
    raise exception 'matcher version is required';
  end if;

  if jsonb_typeof(p_results) <> 'array' then
    raise exception 'p_results must be a JSON array';
  end if;

  select preference.id, preference.updated_at
  into v_preference_id, v_current_preference_updated_at
  from public.user_preferences as preference
  where preference.user_id = p_user_id
  for update;

  if v_preference_id is null then
    raise exception 'user preferences do not exist';
  end if;

  if v_current_preference_updated_at is distinct from p_preference_updated_at then
    raise exception 'user preferences changed during matching';
  end if;

  select count(*)
  into v_expected_count
  from public.jobs as job
  join public.companies as company on company.id = job.company_id
  where company.owner_id = p_user_id
    and job.status = 'open';

  v_result_count := jsonb_array_length(p_results);
  if v_result_count <> v_expected_count then
    raise exception 'match results do not cover the current open-job snapshot';
  end if;

  if (
    select count(distinct value ->> 'job_id')
    from jsonb_array_elements(p_results)
  ) <> v_result_count then
    raise exception 'match results contain duplicate job ids';
  end if;

  for v_result in select value from jsonb_array_elements(p_results)
  loop
    if jsonb_typeof(v_result) <> 'object' then
      raise exception 'match results must be JSON objects';
    end if;

    begin
      v_job_id := (v_result ->> 'job_id')::uuid;
    exception when invalid_text_representation then
      raise exception 'match result contains an invalid job id';
    end;
    v_job_content_hash := nullif(v_result ->> 'job_content_hash', '');

    if v_job_id is null or v_job_content_hash is null then
      raise exception 'match result is missing job identity fields';
    end if;

    if (v_result ->> 'status') not in ('matched', 'review', 'rejected')
      or (v_result ->> 'career_level') not in (
        'new_grad', 'entry_level', 'early_career', 'experienced', 'unknown'
      )
      or (v_result ->> 'sponsorship_status') not in (
        'available', 'unavailable', 'unknown'
      )
      or jsonb_typeof(v_result -> 'match_reasons') <> 'array'
      or jsonb_typeof(v_result -> 'review_reasons') <> 'array'
      or jsonb_typeof(v_result -> 'rejection_reasons') <> 'array'
    then
      raise exception 'match result contains invalid decision data';
    end if;

    select job.content_hash
    into v_current_job_content_hash
    from public.jobs as job
    where job.id = v_job_id
      and job.status = 'open'
      and exists (
        select 1
        from public.companies as company
        where company.id = job.company_id
          and company.owner_id = p_user_id
      )
    for update;

    if v_current_job_content_hash is null then
      raise exception 'match result references an unavailable job';
    end if;

    if v_current_job_content_hash <> v_job_content_hash then
      raise exception 'job changed during matching';
    end if;

    insert into public.job_matches (
      user_id,
      preference_id,
      job_id,
      status,
      career_level,
      sponsorship_status,
      match_reasons,
      review_reasons,
      rejection_reasons,
      preference_updated_at,
      job_content_hash,
      matcher_version,
      evaluated_at
    ) values (
      p_user_id,
      v_preference_id,
      v_job_id,
      (v_result ->> 'status')::public.job_match_status,
      v_result ->> 'career_level',
      v_result ->> 'sponsorship_status',
      v_result -> 'match_reasons',
      v_result -> 'review_reasons',
      v_result -> 'rejection_reasons',
      p_preference_updated_at,
      v_job_content_hash,
      trim(p_matcher_version),
      now()
    )
    on conflict (user_id, job_id) do update
    set preference_id = excluded.preference_id,
        status = excluded.status,
        career_level = excluded.career_level,
        sponsorship_status = excluded.sponsorship_status,
        match_reasons = excluded.match_reasons,
        review_reasons = excluded.review_reasons,
        rejection_reasons = excluded.rejection_reasons,
        preference_updated_at = excluded.preference_updated_at,
        job_content_hash = excluded.job_content_hash,
        matcher_version = excluded.matcher_version,
        evaluated_at = excluded.evaluated_at;

    case v_result ->> 'status'
      when 'matched' then v_matched := v_matched + 1;
      when 'review' then v_review := v_review + 1;
      when 'rejected' then v_rejected := v_rejected + 1;
    end case;
  end loop;

  delete from public.job_matches as match
  where match.user_id = p_user_id
    and not exists (
      select 1
      from jsonb_array_elements(p_results) as result(value)
      where (result.value ->> 'job_id')::uuid = match.job_id
    );

  return jsonb_build_object(
    'evaluated', v_result_count,
    'matched', v_matched,
    'review', v_review,
    'rejected', v_rejected
  );
end;
$$;

revoke all on function public.get_matching_context(uuid) from public, anon, authenticated;
revoke all on function public.persist_job_match_results(uuid, timestamptz, text, jsonb)
  from public, anon, authenticated;

grant execute on function public.get_matching_context(uuid) to service_role;
grant execute on function public.persist_job_match_results(uuid, timestamptz, text, jsonb)
  to service_role;
