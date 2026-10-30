import { afterEach, describe, expect, it } from "vitest";

import { getPublicSupabaseEnv, getServerSupabaseEnv } from "./env";

const originalEnvironment = { ...process.env };

afterEach(() => {
  process.env = { ...originalEnvironment };
});

describe("Supabase environment boundaries", () => {
  it("accepts browser-safe public configuration", () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-value";

    expect(getPublicSupabaseEnv()).toEqual({
      anonKey: "anon-value",
      url: "https://project.supabase.co",
    });
  });

  it("requires the unprefixed service-role key for privileged clients", () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-value";
    delete process.env.SUPABASE_SERVICE_ROLE_KEY;

    expect(() => getServerSupabaseEnv()).toThrow("SUPABASE_SERVICE_ROLE_KEY");
  });
});
