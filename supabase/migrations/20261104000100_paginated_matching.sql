drop function public.get_matching_context(uuid);
drop function public.persist_job_match_results(uuid, timestamptz, text, jsonb);

create index jobs_company_status_id_idx
  on public.jobs (company_id, status, id);

create function public.get_matching_context_page(
  p_user_id uuid,
  p_after_job_id uuid default null,
  p_limit integer default 100,
  p_matcher_version text default 'deterministic-v1'
)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  v_preference public.user_preferences%rowtype;
  v_rows jsonb;
  v_jobs jsonb;
  v_has_more boolean;
  v_next_cursor uuid;
begin
  if p_limit < 1 or p_limit > 250 then
    raise exception 'p_limit must be between 1 and 250' using errcode = '22023';
  end if;
  if p_matcher_version is null or length(trim(p_matcher_version)) = 0 then
    raise exception 'matcher version is required' using errcode = '22023';
  end if;

  select preference.*
  into v_preference
  from public.user_preferences as preference
  where preference.user_id = p_user_id;

  if v_preference.id is null then
    raise exception 'user preferences do not exist' using errcode = 'P0002';
  end if;

  select
    coalesce(jsonb_agg(candidate.payload order by candidate.job_id), '[]'::jsonb),
    count(*) > p_limit
  into v_rows, v_has_more
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
    left join public.job_matches as existing_match
      on existing_match.user_id = p_user_id
      and existing_match.job_id = job.id
    where company.owner_id = p_user_id
      and job.status = 'open'
      and (p_after_job_id is null or job.id > p_after_job_id)
      and (
        existing_match.id is null
        or existing_match.preference_id <> v_preference.id
        or existing_match.preference_updated_at is distinct from v_preference.updated_at
        or existing_match.job_content_hash <> job.content_hash
        or existing_match.matcher_version <> trim(p_matcher_version)
      )
    order by job.id
    limit p_limit + 1
  ) as candidate;

  if v_has_more then
    v_jobs := v_rows - p_limit;
    v_next_cursor := (v_jobs -> -1 ->> 'id')::uuid;
  else
    v_jobs := v_rows;
    v_next_cursor := null;
  end if;

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
    'jobs', v_jobs,
    'has_more', v_has_more,
    'next_cursor', v_next_cursor
  );
end;
$$;

create function public.persist_job_match_results_page(
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
  v_result_count integer;
  v_matched integer := 0;
  v_review integer := 0;
  v_rejected integer := 0;
begin
  if p_matcher_version is null or length(trim(p_matcher_version)) = 0 then
    raise exception 'matcher version is required' using errcode = '22023';
  end if;
  if jsonb_typeof(p_results) <> 'array' then
    raise exception 'p_results must be a JSON array' using errcode = '22023';
  end if;

  v_result_count := jsonb_array_length(p_results);
  if v_result_count > 250 then
    raise exception 'match result page cannot exceed 250 jobs' using errcode = '22023';
  end if;
  if (
    select count(distinct value ->> 'job_id')
    from jsonb_array_elements(p_results)
  ) <> v_result_count then
    raise exception 'match results contain duplicate job ids';
  end if;

  select preference.id, preference.updated_at
  into v_preference_id, v_current_preference_updated_at
  from public.user_preferences as preference
  where preference.user_id = p_user_id
  for update;

  if v_preference_id is null then
    raise exception 'user preferences do not exist' using errcode = 'P0002';
  end if;
  if v_current_preference_updated_at is distinct from p_preference_updated_at then
    raise exception 'user preferences changed during matching';
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

  return jsonb_build_object(
    'evaluated', v_result_count,
    'matched', v_matched,
    'review', v_review,
    'rejected', v_rejected
  );
end;
$$;

create function public.finalize_job_match_results(
  p_user_id uuid,
  p_preference_updated_at timestamptz,
  p_matcher_version text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_preference_id uuid;
  v_current_preference_updated_at timestamptz;
  v_removed integer;
begin
  if p_matcher_version is null or length(trim(p_matcher_version)) = 0 then
    raise exception 'matcher version is required' using errcode = '22023';
  end if;

  select preference.id, preference.updated_at
  into v_preference_id, v_current_preference_updated_at
  from public.user_preferences as preference
  where preference.user_id = p_user_id
  for update;

  if v_preference_id is null then
    raise exception 'user preferences do not exist' using errcode = 'P0002';
  end if;
  if v_current_preference_updated_at is distinct from p_preference_updated_at then
    raise exception 'user preferences changed during matching';
  end if;

  if exists (
    select 1
    from public.jobs as job
    join public.companies as company on company.id = job.company_id
    left join public.job_matches as existing_match
      on existing_match.user_id = p_user_id
      and existing_match.job_id = job.id
    where company.owner_id = p_user_id
      and job.status = 'open'
      and (
        existing_match.id is null
        or existing_match.preference_id <> v_preference_id
        or existing_match.preference_updated_at is distinct from p_preference_updated_at
        or existing_match.job_content_hash <> job.content_hash
        or existing_match.matcher_version <> trim(p_matcher_version)
      )
  ) then
    raise exception 'matching candidates remain unprocessed';
  end if;

  delete from public.job_matches as existing_match
  where existing_match.user_id = p_user_id
    and not exists (
      select 1
      from public.jobs as job
      join public.companies as company on company.id = job.company_id
      where job.id = existing_match.job_id
        and job.status = 'open'
        and company.owner_id = p_user_id
    );
  get diagnostics v_removed = row_count;

  return jsonb_build_object('removed', v_removed);
end;
$$;

revoke all on function public.get_matching_context_page(uuid, uuid, integer, text)
  from public, anon, authenticated;
revoke all on function public.persist_job_match_results_page(uuid, timestamptz, text, jsonb)
  from public, anon, authenticated;
revoke all on function public.finalize_job_match_results(uuid, timestamptz, text)
  from public, anon, authenticated;

grant execute on function public.get_matching_context_page(uuid, uuid, integer, text)
  to service_role;
grant execute on function public.persist_job_match_results_page(uuid, timestamptz, text, jsonb)
  to service_role;
grant execute on function public.finalize_job_match_results(uuid, timestamptz, text)
  to service_role;
