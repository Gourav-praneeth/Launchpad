alter function public.create_watchlist_company(text, text, text, integer)
  security definer;
alter function public.set_company_monitoring(uuid, boolean)
  security definer;

revoke insert, update, delete on public.companies from authenticated;
revoke insert, update, delete on public.sources from authenticated;
revoke insert, update, delete on public.user_preferences from authenticated;

grant select on public.companies, public.sources, public.user_preferences
  to authenticated;
