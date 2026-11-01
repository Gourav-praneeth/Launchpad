create function public.set_job_workflow_status(
  target_job_id uuid,
  target_status public.application_status
)
returns public.user_jobs
language plpgsql
security invoker
set search_path = ''
as $$
declare
  current_status public.application_status;
  result_row public.user_jobs;
begin
  if auth.uid() is null then
    raise exception 'authentication is required' using errcode = '42501';
  end if;

  if target_status is null or target_status not in ('new', 'saved', 'applied', 'not_interested') then
    raise exception 'unsupported workflow status' using errcode = '22023';
  end if;

  if not public.owns_job(target_job_id) then
    raise exception 'job is not visible to the authenticated user' using errcode = '42501';
  end if;

  select interaction.application_status
  into current_status
  from public.user_jobs as interaction
  where interaction.user_id = auth.uid()
    and interaction.job_id = target_job_id;

  if found
    and current_status in ('applied', 'interviewing', 'rejected', 'closed', 'not_interested')
    and target_status is distinct from current_status
  then
    raise exception 'workflow status cannot move from % to %', current_status, target_status
      using errcode = '22023';
  end if;

  insert into public.user_jobs (
    user_id,
    job_id,
    application_status,
    saved_at,
    applied_at
  )
  values (
    auth.uid(),
    target_job_id,
    target_status,
    case when target_status = 'saved' then now() else null end,
    case when target_status = 'applied' then now() else null end
  )
  on conflict (user_id, job_id) do update
  set application_status = excluded.application_status,
      saved_at = case
        when excluded.application_status = 'saved'
          then coalesce(public.user_jobs.saved_at, now())
        when excluded.application_status in ('new', 'not_interested')
          then null
        else public.user_jobs.saved_at
      end,
      applied_at = case
        when excluded.application_status = 'applied'
          then coalesce(public.user_jobs.applied_at, now())
        else public.user_jobs.applied_at
      end
  returning * into result_row;

  return result_row;
end;
$$;

revoke all on function public.set_job_workflow_status(uuid, public.application_status)
  from public, anon;
grant execute on function public.set_job_workflow_status(uuid, public.application_status)
  to authenticated;

