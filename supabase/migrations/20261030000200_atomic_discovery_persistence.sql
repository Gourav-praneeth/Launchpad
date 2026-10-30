alter table public.jobs
add column source_updated_at timestamptz;

create function public.persist_discovery_check(
  p_source_id uuid,
  p_started_at timestamptz,
  p_completed_at timestamptz,
  p_outcome public.source_check_outcome,
  p_listings jsonb,
  p_listings_fetched integer,
  p_error_code text,
  p_error_summary text,
  p_http_status integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_company_id uuid;
  v_source_check_id uuid;
  v_listing jsonb;
  v_job_id uuid;
  v_existing_hash text;
  v_existing_status public.job_status;
  v_existing_last_seen_at timestamptz;
  v_external_job_id text;
  v_dedupe_key text;
  v_title text;
  v_normalized_title text;
  v_apply_url text;
  v_canonical_apply_url text;
  v_content_hash text;
  v_content_changed boolean;
  v_inserted integer := 0;
  v_updated integer := 0;
  v_unchanged integer := 0;
  v_reopened integer := 0;
  v_accepted integer;
begin
  if p_completed_at < p_started_at then
    raise exception 'discovery completion cannot precede its start';
  end if;

  if jsonb_typeof(p_listings) <> 'array' then
    raise exception 'p_listings must be a JSON array';
  end if;

  v_accepted := jsonb_array_length(p_listings);

  if p_listings_fetched < v_accepted or p_listings_fetched < 0 then
    raise exception 'invalid source listing counts';
  end if;

  if p_outcome = 'successful' and (
    p_listings_fetched <> v_accepted
    or p_error_code is not null
    or p_error_summary is not null
  ) then
    raise exception 'successful source checks cannot contain rejected items or errors';
  end if;

  if p_outcome = 'partial' and (
    p_listings_fetched <= v_accepted
    or p_error_code is null
    or p_error_summary is null
  ) then
    raise exception 'partial source checks require rejected items and an error summary';
  end if;

  if p_outcome = 'failed' and (
    v_accepted <> 0
    or p_listings_fetched <> 0
    or p_error_code is null
    or p_error_summary is null
  ) then
    raise exception 'failed source checks cannot contain listings and require an error';
  end if;

  if p_http_status is not null and (p_http_status < 100 or p_http_status > 599) then
    raise exception 'invalid HTTP status';
  end if;

  -- Lock the source row so overlapping runs for one source cannot race each other.
  select source.company_id
  into v_company_id
  from public.sources as source
  where source.id = p_source_id
  for update;

  if v_company_id is null then
    raise exception 'source does not exist';
  end if;

  -- A failed request is evidence about source health, never evidence that jobs closed.
  if p_outcome <> 'failed' then
    for v_listing in
      select value from jsonb_array_elements(p_listings)
    loop
      if jsonb_typeof(v_listing) <> 'object' then
        raise exception 'persisted listings must be JSON objects';
      end if;

      v_external_job_id := nullif(trim(v_listing ->> 'external_job_id'), '');
      v_dedupe_key := nullif(trim(v_listing ->> 'dedupe_key'), '');
      v_title := nullif(trim(v_listing ->> 'title'), '');
      v_normalized_title := nullif(trim(v_listing ->> 'normalized_title'), '');
      v_apply_url := nullif(trim(v_listing ->> 'apply_url'), '');
      v_canonical_apply_url := nullif(trim(v_listing ->> 'canonical_apply_url'), '');
      v_content_hash := nullif(trim(v_listing ->> 'content_hash'), '');

      if v_dedupe_key is null
        or v_title is null
        or v_normalized_title is null
        or v_apply_url is null
        or v_canonical_apply_url is null
        or v_content_hash is null
      then
        raise exception 'persisted listing is missing a required field';
      end if;

      v_job_id := null;
      v_existing_hash := null;
      v_existing_status := null;
      v_existing_last_seen_at := null;

      if v_external_job_id is not null then
        select job.id, job.content_hash, job.status, job.last_seen_at
        into v_job_id, v_existing_hash, v_existing_status, v_existing_last_seen_at
        from public.jobs as job
        where job.source_id = p_source_id
          and job.external_job_id = v_external_job_id
        for update;
      end if;

      if v_job_id is null then
        select job.id, job.content_hash, job.status, job.last_seen_at
        into v_job_id, v_existing_hash, v_existing_status, v_existing_last_seen_at
        from public.jobs as job
        where job.source_id = p_source_id
          and job.dedupe_key = v_dedupe_key
        for update;
      end if;

      if v_job_id is null then
        insert into public.jobs (
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
          employer_posted_at,
          source_updated_at,
          first_seen_at,
          last_seen_at,
          last_verified_at,
          status,
          content_hash
        ) values (
          v_company_id,
          p_source_id,
          v_external_job_id,
          v_dedupe_key,
          v_title,
          v_normalized_title,
          nullif(trim(v_listing ->> 'location'), ''),
          nullif(trim(v_listing ->> 'workplace_type'), ''),
          nullif(trim(v_listing ->> 'employment_type'), ''),
          nullif(v_listing ->> 'description', ''),
          v_apply_url,
          v_canonical_apply_url,
          (v_listing ->> 'employer_posted_at')::timestamptz,
          (v_listing ->> 'source_updated_at')::timestamptz,
          p_completed_at,
          p_completed_at,
          p_completed_at,
          'open',
          v_content_hash
        )
        returning id into v_job_id;

        insert into public.job_events (job_id, event_type, detected_at, details)
        values (
          v_job_id,
          'first_seen',
          p_completed_at,
          jsonb_build_object('source_check_outcome', p_outcome)
        );
        v_inserted := v_inserted + 1;
        continue;
      end if;

      -- Do not let an older overlapping response overwrite a newer observation.
      if p_completed_at < v_existing_last_seen_at then
        v_unchanged := v_unchanged + 1;
        continue;
      end if;

      v_content_changed := v_existing_hash is distinct from v_content_hash;

      update public.jobs
      set external_job_id = coalesce(v_external_job_id, external_job_id),
          dedupe_key = v_dedupe_key,
          title = v_title,
          normalized_title = v_normalized_title,
          location = nullif(trim(v_listing ->> 'location'), ''),
          workplace_type = nullif(trim(v_listing ->> 'workplace_type'), ''),
          employment_type = nullif(trim(v_listing ->> 'employment_type'), ''),
          description = nullif(v_listing ->> 'description', ''),
          apply_url = v_apply_url,
          canonical_apply_url = v_canonical_apply_url,
          employer_posted_at = (v_listing ->> 'employer_posted_at')::timestamptz,
          source_updated_at = coalesce(
            (v_listing ->> 'source_updated_at')::timestamptz,
            source_updated_at
          ),
          last_seen_at = p_completed_at,
          last_verified_at = p_completed_at,
          status = 'open',
          content_hash = v_content_hash
      where id = v_job_id;

      if v_content_changed then
        insert into public.job_events (job_id, event_type, detected_at, details)
        values (
          v_job_id,
          'updated',
          p_completed_at,
          jsonb_build_object(
            'previous_content_hash', v_existing_hash,
            'content_hash', v_content_hash
          )
        );
        v_updated := v_updated + 1;
      else
        v_unchanged := v_unchanged + 1;
      end if;

      if v_existing_status <> 'open' then
        insert into public.job_events (job_id, event_type, detected_at, details)
        values (
          v_job_id,
          'reopened',
          p_completed_at,
          jsonb_build_object('previous_status', v_existing_status)
        );
        v_reopened := v_reopened + 1;
      end if;
    end loop;
  end if;

  insert into public.source_checks (
    source_id,
    started_at,
    completed_at,
    outcome,
    listings_fetched,
    listings_accepted,
    http_status,
    error_code,
    error_summary
  ) values (
    p_source_id,
    p_started_at,
    p_completed_at,
    p_outcome,
    p_listings_fetched,
    v_accepted,
    p_http_status,
    p_error_code,
    p_error_summary
  )
  returning id into v_source_check_id;

  update public.sources
  set last_attempt_at = greatest(coalesce(last_attempt_at, p_completed_at), p_completed_at),
      last_success_at = case
        when p_outcome = 'successful'
          then greatest(coalesce(last_success_at, p_completed_at), p_completed_at)
        else last_success_at
      end,
      last_error = case
        when last_attempt_at is null or p_completed_at >= last_attempt_at then
          case when p_outcome = 'successful' then null else p_error_summary end
        else last_error
      end
  where id = p_source_id;

  return jsonb_build_object(
    'source_check_id', v_source_check_id,
    'inserted', v_inserted,
    'updated', v_updated,
    'unchanged', v_unchanged,
    'reopened', v_reopened
  );
end;
$$;

revoke all on function public.persist_discovery_check(
  uuid,
  timestamptz,
  timestamptz,
  public.source_check_outcome,
  jsonb,
  integer,
  text,
  text,
  integer
) from public, anon, authenticated;

grant execute on function public.persist_discovery_check(
  uuid,
  timestamptz,
  timestamptz,
  public.source_check_outcome,
  jsonb,
  integer,
  text,
  text,
  integer
) to service_role;
