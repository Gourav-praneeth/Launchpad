const requireValue = (name: string, value: string | undefined): string => {
  if (!value || value.includes("your-")) {
    throw new Error(`Missing or placeholder environment variable: ${name}`);
  }

  return value;
};

const requireUrl = (name: string, value: string | undefined): string => {
  const parsed = new URL(requireValue(name, value));

  if (parsed.protocol !== "https:" && parsed.hostname !== "127.0.0.1") {
    throw new Error(
      `${name} must use HTTPS unless it points to local Supabase.`,
    );
  }

  return parsed.toString().replace(/\/$/, "");
};

export const getPublicSupabaseEnv = () => ({
  anonKey: requireValue(
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  ),
  url: requireUrl(
    "NEXT_PUBLIC_SUPABASE_URL",
    process.env.NEXT_PUBLIC_SUPABASE_URL,
  ),
});

export const getServerSupabaseEnv = () => ({
  ...getPublicSupabaseEnv(),
  serviceRoleKey: requireValue(
    "SUPABASE_SERVICE_ROLE_KEY",
    process.env.SUPABASE_SERVICE_ROLE_KEY,
  ),
});
