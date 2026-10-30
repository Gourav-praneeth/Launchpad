import "server-only";

import { createClient } from "@supabase/supabase-js";

import { getServerSupabaseEnv } from "@/lib/env";

export const createSupabaseAdminClient = () => {
  const { serviceRoleKey, url } = getServerSupabaseEnv();

  return createClient(url, serviceRoleKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  });
};
