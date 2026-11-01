alter table public.sources
  add constraint sources_supported_type check (source_type = 'greenhouse'),
  add constraint sources_supported_url check (
    source_url ~ '^https://boards-api\.greenhouse\.io/v1/boards/[A-Za-z0-9_-]+/jobs/?$'
  );

create function public.create_watchlist_company(
  company_name text,
  company_careers_url text,
  greenhouse_source_url text,
  interval_minutes integer default 60
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  new_company public.companies;
  new_source public.sources;
begin
  if auth.uid() is null then
    raise exception 'authentication is required' using errcode = '42501';
  end if;

  company_name := trim(company_name);
  company_careers_url := trim(company_careers_url);
  greenhouse_source_url := regexp_replace(trim(greenhouse_source_url), '/$', '');

  if company_name is null or length(company_name) = 0 or length(company_name) > 120 then
    raise exception 'company name must be between 1 and 120 characters' using errcode = '22023';
  end if;
  if company_careers_url is null or company_careers_url !~ '^https://' then
    raise exception 'careers URL must use HTTPS' using errcode = '22023';
  end if;
  if greenhouse_source_url is null or greenhouse_source_url !~
    '^https://boards-api\.greenhouse\.io/v1/boards/[A-Za-z0-9_-]+/jobs$'
  then
    raise exception 'source URL must be an official Greenhouse list-jobs endpoint'
      using errcode = '22023';
  end if;
  if interval_minutes not in (15, 30, 60, 180, 360) then
    raise exception 'unsupported check interval' using errcode = '22023';
  end if;

  insert into public.companies (owner_id, name, careers_url)
  values (auth.uid(), company_name, company_careers_url)
  returning * into new_company;

  insert into public.sources (
    company_id,
    source_type,
    source_url,
    check_interval_minutes
  )
  values (
    new_company.id,
    'greenhouse',
    greenhouse_source_url,
    interval_minutes
  )
  returning * into new_source;

  return jsonb_build_object(
    'company_id', new_company.id,
    'source_id', new_source.id
  );
end;
$$;

create function public.set_company_monitoring(
  target_company_id uuid,
  monitoring_active boolean
)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if auth.uid() is null then
    raise exception 'authentication is required' using errcode = '42501';
  end if;
  if target_company_id is null or monitoring_active is null then
    raise exception 'company and monitoring state are required' using errcode = '22023';
  end if;
  if not public.owns_company(target_company_id) then
    raise exception 'company is not visible to the authenticated user' using errcode = '42501';
  end if;

  update public.companies
  set is_active = monitoring_active
  where id = target_company_id;

  update public.sources
  set is_active = monitoring_active
  where company_id = target_company_id;
end;
$$;

create function public.update_job_preferences(
  preference_target_titles jsonb,
  preference_career_levels jsonb,
  preference_employment_types jsonb,
  preference_locations jsonb,
  preference_workplace_types jsonb,
  preference_sponsorship text,
  preference_include_keywords jsonb,
  preference_exclude_keywords jsonb,
  preference_include_senior_roles boolean,
  preference_alert_frequency public.alert_frequency
)
returns public.user_preferences
language plpgsql
security definer
set search_path = ''
as $$
declare
  authenticated_user_id uuid := auth.uid();
  updated_preference public.user_preferences;
begin
  if authenticated_user_id is null then
    raise exception 'authentication is required' using errcode = '42501';
  end if;
  if preference_include_senior_roles is null or preference_alert_frequency is null then
    raise exception 'preference booleans and frequency are required' using errcode = '22023';
  end if;

  update public.user_preferences
  set target_titles = preference_target_titles,
      career_levels = preference_career_levels,
      employment_types = preference_employment_types,
      locations = preference_locations,
      workplace_types = preference_workplace_types,
      sponsorship_preference = preference_sponsorship,
      include_keywords = preference_include_keywords,
      exclude_keywords = preference_exclude_keywords,
      include_senior_roles = preference_include_senior_roles,
      alert_frequency = preference_alert_frequency
  where user_id = authenticated_user_id
  returning * into updated_preference;

  if updated_preference.id is null then
    raise exception 'user preferences do not exist' using errcode = 'P0002';
  end if;

  delete from public.job_matches
  where user_id = authenticated_user_id;

  return updated_preference;
end;
$$;

revoke all on function public.create_watchlist_company(text, text, text, integer)
  from public, anon;
revoke all on function public.set_company_monitoring(uuid, boolean)
  from public, anon;
revoke all on function public.update_job_preferences(
  jsonb, jsonb, jsonb, jsonb, jsonb, text, jsonb, jsonb, boolean, public.alert_frequency
) from public, anon;

grant execute on function public.create_watchlist_company(text, text, text, integer)
  to authenticated;
grant execute on function public.set_company_monitoring(uuid, boolean)
  to authenticated;
grant execute on function public.update_job_preferences(
  jsonb, jsonb, jsonb, jsonb, jsonb, text, jsonb, jsonb, boolean, public.alert_frequency
) to authenticated;
