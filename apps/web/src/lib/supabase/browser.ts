"use client";

import { createBrowserClient } from "@supabase/ssr";

import { getPublicSupabaseEnv } from "@/lib/env";

export const createSupabaseBrowserClient = () => {
  const { anonKey, url } = getPublicSupabaseEnv();
  return createBrowserClient(url, anonKey);
};
