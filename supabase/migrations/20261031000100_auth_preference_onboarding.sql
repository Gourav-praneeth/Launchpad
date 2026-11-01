create function public.create_default_user_preferences()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.user_preferences (user_id)
  values (new.id)
  on conflict (user_id) do nothing;
  return new;
end;
$$;

revoke all on function public.create_default_user_preferences() from public, anon, authenticated;

create trigger auth_users_create_default_preferences
after insert on auth.users
for each row execute function public.create_default_user_preferences();

insert into public.user_preferences (user_id)
select auth_user.id
from auth.users as auth_user
on conflict (user_id) do nothing;
