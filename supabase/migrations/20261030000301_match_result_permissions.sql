-- Supabase may grant table privileges to API roles through database-level
-- default privileges. Derived matching decisions remain worker-owned.
revoke insert, update, delete on public.job_matches from authenticated, anon;
