alter table public.sources
  add column consecutive_failures integer not null default 0
    check (consecutive_failures >= 0),
  add column backoff_until timestamptz;

alter table public.user_preferences
  add column notifications_enabled_at timestamptz not null default now();

alter table public.notifications
  add column available_at timestamptz not null default now();

create type public.notification_delivery_status as enum ('pending', 'sent', 'failed');

create table public.notification_deliveries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  dedupe_key text not null unique check (length(trim(dedupe_key)) between 1 and 256),
  status public.notification_delivery_status not null default 'pending',
  recipient_email text not null check (recipient_email ~ '^[^[:space:]@]+@[^[:space:]@]+$'),
  subject text not null check (length(trim(subject)) > 0),
  payload jsonb not null check (
    jsonb_typeof(payload) = 'array' and jsonb_array_length(payload) > 0
  ),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  next_attempt_at timestamptz not null default now(),
  claimed_at timestamptz,
  provider_message_id text,
  sent_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint notification_deliveries_sent_state check (
    (status = 'sent' and sent_at is not null and provider_message_id is not null)
    or (status <> 'sent' and sent_at is null)
  )
);

alter table public.notifications
  add column delivery_id uuid references public.notification_deliveries(id) on delete set null;

create index notification_deliveries_queue_idx
  on public.notification_deliveries (status, next_attempt_at, created_at)
  where status = 'pending';
create index notifications_unbatched_queue_idx
  on public.notifications (next_attempt_at, user_id, created_at)
  where status = 'pending' and delivery_id is null;

create trigger notification_deliveries_set_updated_at
before update on public.notification_deliveries
for each row execute function public.set_updated_at();

create function public.update_source_retry_state()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  next_failure_count integer;
  delay_minutes integer;
begin
  if new.outcome = 'successful' then
    update public.sources
    set consecutive_failures = 0,
        backoff_until = null
    where id = new.source_id;
    return new;
  end if;

  select least(source.consecutive_failures + 1, 10)
  into next_failure_count
  from public.sources as source
  where source.id = new.source_id
  for update;

  delay_minutes := least(360, 5 * power(2, least(next_failure_count - 1, 6))::integer);
  update public.sources
  set consecutive_failures = next_failure_count,
      backoff_until = new.completed_at + make_interval(mins => delay_minutes)
  where id = new.source_id;
  return new;
end;
$$;

revoke all on function public.update_source_retry_state() from public, anon, authenticated;

create trigger source_checks_update_retry_state
after insert on public.source_checks
for each row execute function public.update_source_retry_state();

create function public.get_automation_targets()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'source_ids', coalesce((
      select jsonb_agg(source.id order by source.id)
      from public.sources as source
      join public.companies as company on company.id = source.company_id
      where source.is_active
        and company.is_active
        and (source.backoff_until is null or source.backoff_until <= now())
        and (
          source.last_attempt_at is null
          or source.last_attempt_at
            + make_interval(mins => source.check_interval_minutes) <= now()
        )
    ), '[]'::jsonb),
    'user_ids', coalesce((
      select jsonb_agg(preference.user_id order by preference.user_id)
      from public.user_preferences as preference
      where exists (
        select 1
        from public.companies as company
        where company.owner_id = preference.user_id
          and company.is_active
      )
    ), '[]'::jsonb)
  );
$$;

create function public.queue_match_notifications(target_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  queued_count integer;
begin
  if target_user_id is null then
    raise exception 'user id is required' using errcode = '22023';
  end if;
  if not exists (
    select 1 from public.user_preferences where user_id = target_user_id
  ) then
    raise exception 'user preferences do not exist' using errcode = 'P0002';
  end if;

  insert into public.notifications (
    user_id,
    job_id,
    channel,
    dedupe_key,
    status,
    next_attempt_at,
    available_at
  )
  select
    match.user_id,
    match.job_id,
    'email',
    concat('job-match/', match.user_id, '/', match.job_id),
    'pending',
    schedule.available_at,
    schedule.available_at
  from public.job_matches as match
  join public.jobs as job on job.id = match.job_id
  join public.user_preferences as preference on preference.user_id = match.user_id
  cross join lateral (
    select case preference.alert_frequency
      when 'immediate' then now()
      when 'hourly_digest' then date_trunc('hour', now()) + interval '1 hour'
      when 'daily_digest' then date_trunc('day', now()) + interval '1 day'
    end as available_at
  ) as schedule
  where match.user_id = target_user_id
    and match.status = 'matched'
    and job.status = 'open'
    and job.first_seen_at >= preference.notifications_enabled_at
  on conflict (user_id, dedupe_key) do nothing;

  get diagnostics queued_count = row_count;
  return jsonb_build_object('queued', queued_count);
end;
$$;

create function public.claim_notification_delivery(
  maximum_items integer default 50,
  lease_minutes integer default 15
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  delivery public.notification_deliveries%rowtype;
  selected_user_id uuid;
  selected_ids uuid[];
  selected_payload jsonb;
  selected_email text;
  delivery_key text;
begin
  if maximum_items < 1 or maximum_items > 100 then
    raise exception 'maximum_items must be between 1 and 100' using errcode = '22023';
  end if;
  if lease_minutes < 1 or lease_minutes > 60 then
    raise exception 'lease_minutes must be between 1 and 60' using errcode = '22023';
  end if;

  select candidate.*
  into delivery
  from public.notification_deliveries as candidate
  where candidate.status = 'pending'
    and candidate.next_attempt_at <= now()
    and (
      candidate.claimed_at is null
      or candidate.claimed_at <= now() - make_interval(mins => lease_minutes)
    )
  order by candidate.next_attempt_at, candidate.created_at
  for update skip locked
  limit 1;

  if delivery.id is null then
    select notification.user_id
    into selected_user_id
    from public.notifications as notification
    where notification.status = 'pending'
      and notification.delivery_id is null
      and notification.next_attempt_at <= now()
      and notification.available_at <= now()
    order by notification.next_attempt_at, notification.created_at
    for update skip locked
    limit 1;

    if selected_user_id is null then
      return null;
    end if;

    select auth_user.email
    into selected_email
    from auth.users as auth_user
    where auth_user.id = selected_user_id;
    if selected_email is null or length(trim(selected_email)) = 0 then
      raise exception 'notification recipient has no email address';
    end if;

    with selected as (
      select notification.id, notification.job_id
      from public.notifications as notification
      where notification.user_id = selected_user_id
        and notification.status = 'pending'
        and notification.delivery_id is null
        and notification.next_attempt_at <= now()
        and notification.available_at <= now()
      order by notification.created_at, notification.id
      for update skip locked
      limit maximum_items
    )
    select
      array_agg(selected.id order by selected.id),
      jsonb_agg(
        jsonb_build_object(
          'job_id', job.id,
          'title', job.title,
          'company', company.name,
          'location', job.location,
          'workplace_type', job.workplace_type,
          'employment_type', job.employment_type,
          'apply_url', job.apply_url,
          'first_seen_at', job.first_seen_at
        ) order by job.first_seen_at desc, job.id
      )
    into selected_ids, selected_payload
    from selected
    join public.jobs as job on job.id = selected.job_id
    join public.companies as company on company.id = job.company_id;

    if selected_ids is null or array_length(selected_ids, 1) = 0 then
      return null;
    end if;

    delivery_key := concat(
      'job-digest/',
      encode(
        extensions.digest(array_to_string(selected_ids, ','), 'sha256'),
        'hex'
      )
    );

    insert into public.notification_deliveries (
      user_id,
      dedupe_key,
      recipient_email,
      subject,
      payload
    ) values (
      selected_user_id,
      delivery_key,
      trim(selected_email),
      case array_length(selected_ids, 1)
        when 1 then 'A fresh Launchpad job match'
        else concat(array_length(selected_ids, 1), ' fresh Launchpad job matches')
      end,
      selected_payload
    )
    returning * into delivery;

    update public.notifications
    set delivery_id = delivery.id
    where id = any(selected_ids);
  end if;

  update public.notification_deliveries
  set attempt_count = attempt_count + 1,
      claimed_at = now()
  where id = delivery.id
  returning * into delivery;

  return jsonb_build_object(
    'id', delivery.id,
    'dedupe_key', delivery.dedupe_key,
    'recipient_email', delivery.recipient_email,
    'subject', delivery.subject,
    'payload', delivery.payload,
    'attempt_count', delivery.attempt_count
  );
end;
$$;

create function public.complete_notification_delivery(
  target_delivery_id uuid,
  delivered boolean,
  provider_id text default null,
  error_summary text default null,
  maximum_attempts integer default 5
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  delivery public.notification_deliveries%rowtype;
  retry_at timestamptz;
begin
  if target_delivery_id is null or delivered is null then
    raise exception 'delivery id and result are required' using errcode = '22023';
  end if;
  if maximum_attempts < 1 or maximum_attempts > 10 then
    raise exception 'maximum_attempts must be between 1 and 10' using errcode = '22023';
  end if;

  select * into delivery
  from public.notification_deliveries
  where id = target_delivery_id
  for update;
  if delivery.id is null then
    raise exception 'notification delivery does not exist' using errcode = 'P0002';
  end if;
  if delivery.status = 'sent' then
    return jsonb_build_object('status', 'sent', 'next_attempt_at', null);
  end if;

  if delivered then
    if provider_id is null or length(trim(provider_id)) = 0 then
      raise exception 'provider id is required for a successful delivery' using errcode = '22023';
    end if;
    update public.notification_deliveries
    set status = 'sent',
        provider_message_id = trim(provider_id),
        sent_at = now(),
        claimed_at = null,
        last_error = null
    where id = delivery.id;
    update public.notifications
    set status = 'sent',
        sent_at = now(),
        provider_message_id = trim(provider_id),
        last_error = null
    where delivery_id = delivery.id;
    return jsonb_build_object('status', 'sent', 'next_attempt_at', null);
  end if;

  if error_summary is null or length(trim(error_summary)) = 0 then
    raise exception 'error summary is required for a failed delivery' using errcode = '22023';
  end if;

  if delivery.attempt_count >= maximum_attempts then
    update public.notification_deliveries
    set status = 'failed',
        claimed_at = null,
        last_error = left(trim(error_summary), 500)
    where id = delivery.id;
    update public.notifications
    set status = 'failed',
        last_error = left(trim(error_summary), 500)
    where delivery_id = delivery.id;
    return jsonb_build_object('status', 'failed', 'next_attempt_at', null);
  end if;

  retry_at := now() + make_interval(
    mins => least(360, 5 * power(2, least(delivery.attempt_count - 1, 6))::integer)
  );
  update public.notification_deliveries
  set status = 'pending',
      next_attempt_at = retry_at,
      claimed_at = null,
      last_error = left(trim(error_summary), 500)
  where id = delivery.id;
  update public.notifications
  set status = 'pending',
      next_attempt_at = retry_at,
      last_error = left(trim(error_summary), 500)
  where delivery_id = delivery.id;
  return jsonb_build_object('status', 'pending', 'next_attempt_at', retry_at);
end;
$$;

alter table public.notification_deliveries enable row level security;

revoke all on table public.notification_deliveries from public, anon, authenticated;
revoke insert, update, delete on public.notifications from authenticated;

revoke all on function public.get_automation_targets() from public, anon, authenticated;
revoke all on function public.queue_match_notifications(uuid) from public, anon, authenticated;
revoke all on function public.claim_notification_delivery(integer, integer)
  from public, anon, authenticated;
revoke all on function public.complete_notification_delivery(uuid, boolean, text, text, integer)
  from public, anon, authenticated;

grant execute on function public.get_automation_targets() to service_role;
grant execute on function public.queue_match_notifications(uuid) to service_role;
grant execute on function public.claim_notification_delivery(integer, integer) to service_role;
grant execute on function public.complete_notification_delivery(uuid, boolean, text, text, integer)
  to service_role;
grant all on table public.notification_deliveries to service_role;
