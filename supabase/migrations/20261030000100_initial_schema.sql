create extension if not exists pgcrypto with schema extensions;

create type public.job_status as enum ('open', 'closed', 'uncertain');
create type public.job_event_type as enum (
  'first_seen',
  'updated',
  'closed',
  'reopened',
  'status_uncertain'
);
create type public.source_check_outcome as enum ('successful', 'partial', 'failed');
create type public.application_status as enum (
  'new',
  'saved',
  'applied',
  'interviewing',
  'rejected',
  'closed',
  'not_interested'
);
create type public.notification_status as enum ('pending', 'sent', 'failed');
create type public.alert_frequency as enum ('immediate', 'hourly_digest', 'daily_digest');

create table public.companies (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (length(trim(name)) > 0),
  careers_url text not null check (careers_url ~ '^https?://'),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index companies_owner_name_unique
  on public.companies (owner_id, lower(name));

create table public.sources (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.companies(id) on delete cascade,
  source_type text not null check (length(trim(source_type)) > 0),
  source_url text not null check (source_url ~ '^https?://'),
  is_active boolean not null default true,
  check_interval_minutes integer not null default 60 check (check_interval_minutes between 5 and 10080),
  last_attempt_at timestamptz,
  last_success_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint sources_company_url_unique unique (company_id, source_url),
  constraint sources_success_after_attempt check (
    last_success_at is null
    or last_attempt_at is null
    or last_success_at <= last_attempt_at
  )
);

create table public.source_checks (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources(id) on delete cascade,
  started_at timestamptz not null,
  completed_at timestamptz not null,
  outcome public.source_check_outcome not null,
  listings_fetched integer not null default 0 check (listings_fetched >= 0),
  listings_accepted integer not null default 0 check (listings_accepted >= 0),
  http_status integer check (http_status between 100 and 599),
  error_code text,
  error_summary text,
  created_at timestamptz not null default now(),
  constraint source_checks_completed_after_start check (completed_at >= started_at),
  constraint source_checks_accepted_lte_fetched check (listings_accepted <= listings_fetched),
  constraint source_checks_success_has_no_error check (
    outcome <> 'successful'
    or (error_code is null and error_summary is null)
  )
);

create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.companies(id) on delete cascade,
  source_id uuid not null references public.sources(id) on delete cascade,
  external_job_id text,
  dedupe_key text not null check (length(trim(dedupe_key)) > 0),
  title text not null check (length(trim(title)) > 0),
  normalized_title text not null check (length(trim(normalized_title)) > 0),
  location text,
  workplace_type text,
  employment_type text,
  experience_level text not null default 'unknown',
  description text,
  apply_url text not null check (apply_url ~ '^https?://'),
  canonical_apply_url text not null check (canonical_apply_url ~ '^https?://'),
  employer_posted_at timestamptz,
  first_seen_at timestamptz not null,
  last_seen_at timestamptz not null,
  last_verified_at timestamptz,
  status public.job_status not null default 'open',
  content_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint jobs_seen_order check (last_seen_at >= first_seen_at),
  constraint jobs_verified_after_discovery check (
    last_verified_at is null or last_verified_at >= first_seen_at
  ),
  constraint jobs_source_dedupe_key_unique unique (source_id, dedupe_key)
);

create unique index jobs_source_external_job_id_unique
  on public.jobs (source_id, external_job_id)
  where external_job_id is not null;
create index jobs_first_seen_at_idx on public.jobs (first_seen_at desc);
create index jobs_company_id_idx on public.jobs (company_id);
create index jobs_status_idx on public.jobs (status);
create index jobs_canonical_apply_url_idx on public.jobs (canonical_apply_url);

create table public.job_events (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.jobs(id) on delete cascade,
  event_type public.job_event_type not null,
  detected_at timestamptz not null default now(),
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index job_events_job_detected_idx
  on public.job_events (job_id, detected_at desc);

create table public.user_preferences (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  target_titles jsonb not null default '[]'::jsonb,
  career_levels jsonb not null default '[]'::jsonb,
  employment_types jsonb not null default '["full-time"]'::jsonb,
  locations jsonb not null default '[]'::jsonb,
  workplace_types jsonb not null default '[]'::jsonb,
  graduation_window jsonb,
  sponsorship_preference text,
  include_keywords jsonb not null default '[]'::jsonb,
  exclude_keywords jsonb not null default '[]'::jsonb,
  alert_frequency public.alert_frequency not null default 'immediate',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_preferences_sponsorship_check check (
    sponsorship_preference is null
    or sponsorship_preference in ('required', 'not_required', 'any', 'unknown')
  ),
  constraint user_preferences_json_arrays check (
    jsonb_typeof(target_titles) = 'array'
    and jsonb_typeof(career_levels) = 'array'
    and jsonb_typeof(employment_types) = 'array'
    and jsonb_typeof(locations) = 'array'
    and jsonb_typeof(workplace_types) = 'array'
    and jsonb_typeof(include_keywords) = 'array'
    and jsonb_typeof(exclude_keywords) = 'array'
  )
);

create table public.user_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  saved_at timestamptz,
  application_status public.application_status not null default 'new',
  applied_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_jobs_user_job_unique unique (user_id, job_id)
);

create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  job_id uuid not null references public.jobs(id) on delete cascade,
  channel text not null default 'email' check (channel = 'email'),
  dedupe_key text not null check (length(trim(dedupe_key)) > 0),
  status public.notification_status not null default 'pending',
  attempt_count integer not null default 0 check (attempt_count >= 0),
  next_attempt_at timestamptz,
  provider_message_id text,
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  last_error text,
  updated_at timestamptz not null default now(),
  constraint notifications_user_dedupe_unique unique (user_id, dedupe_key),
  constraint notifications_sent_state_check check (
    (status = 'sent' and sent_at is not null)
    or (status <> 'sent' and sent_at is null)
  )
);

create index source_checks_source_started_idx
  on public.source_checks (source_id, started_at desc);
create index notifications_delivery_queue_idx
  on public.notifications (status, next_attempt_at, created_at)
  where status <> 'sent';

create function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create function public.preserve_first_seen_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.first_seen_at is distinct from old.first_seen_at then
    raise exception 'first_seen_at is immutable';
  end if;
  return new;
end;
$$;

create trigger companies_set_updated_at
before update on public.companies
for each row execute function public.set_updated_at();
create trigger sources_set_updated_at
before update on public.sources
for each row execute function public.set_updated_at();
create trigger jobs_set_updated_at
before update on public.jobs
for each row execute function public.set_updated_at();
create trigger jobs_preserve_first_seen_at
before update on public.jobs
for each row execute function public.preserve_first_seen_at();
create trigger user_preferences_set_updated_at
before update on public.user_preferences
for each row execute function public.set_updated_at();
create trigger user_jobs_set_updated_at
before update on public.user_jobs
for each row execute function public.set_updated_at();
create trigger notifications_set_updated_at
before update on public.notifications
for each row execute function public.set_updated_at();

create function public.owns_company(target_company_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.companies
    where id = target_company_id and owner_id = auth.uid()
  );
$$;

create function public.owns_source(target_source_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.sources as source
    join public.companies as company on company.id = source.company_id
    where source.id = target_source_id and company.owner_id = auth.uid()
  );
$$;

create function public.owns_job(target_job_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.jobs as job
    join public.companies as company on company.id = job.company_id
    where job.id = target_job_id and company.owner_id = auth.uid()
  );
$$;

revoke all on function public.owns_company(uuid) from public;
revoke all on function public.owns_source(uuid) from public;
revoke all on function public.owns_job(uuid) from public;
grant execute on function public.owns_company(uuid) to authenticated, service_role;
grant execute on function public.owns_source(uuid) to authenticated, service_role;
grant execute on function public.owns_job(uuid) to authenticated, service_role;

alter table public.companies enable row level security;
alter table public.sources enable row level security;
alter table public.source_checks enable row level security;
alter table public.jobs enable row level security;
alter table public.job_events enable row level security;
alter table public.user_preferences enable row level security;
alter table public.user_jobs enable row level security;
alter table public.notifications enable row level security;

create policy companies_owner_all on public.companies
for all to authenticated
using (owner_id = auth.uid())
with check (owner_id = auth.uid());

create policy sources_owner_all on public.sources
for all to authenticated
using (public.owns_company(company_id))
with check (public.owns_company(company_id));

create policy source_checks_owner_select on public.source_checks
for select to authenticated
using (public.owns_source(source_id));

create policy jobs_owner_select on public.jobs
for select to authenticated
using (public.owns_company(company_id));

create policy job_events_owner_select on public.job_events
for select to authenticated
using (public.owns_job(job_id));

create policy user_preferences_owner_all on public.user_preferences
for all to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

create policy user_jobs_owner_all on public.user_jobs
for all to authenticated
using (user_id = auth.uid() and public.owns_job(job_id))
with check (user_id = auth.uid() and public.owns_job(job_id));

create policy notifications_owner_select on public.notifications
for select to authenticated
using (user_id = auth.uid() and public.owns_job(job_id));

grant usage on schema public to authenticated, service_role;
grant select, insert, update, delete on public.companies to authenticated;
grant select, insert, update, delete on public.sources to authenticated;
grant select on public.source_checks, public.jobs, public.job_events, public.notifications to authenticated;
grant select, insert, update, delete on public.user_preferences, public.user_jobs to authenticated;
grant all on all tables in schema public to service_role;
