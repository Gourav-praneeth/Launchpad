import "server-only";

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { getPublicSupabaseEnv } from "@/lib/env";

export const createSupabaseServerClient = async () => {
  const cookieStore = await cookies();
  const { anonKey, url } = getPublicSupabaseEnv();

  return createServerClient(url, anonKey, {
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (cookiesToSet) => {
        try {
          cookiesToSet.forEach(({ name, options, value }) => {
            cookieStore.set(name, value, options);
          });
        } catch {
          // Server Components cannot write cookies. A future auth proxy will
          // refresh sessions before rendering protected routes.
        }
      },
    },
  });
};
