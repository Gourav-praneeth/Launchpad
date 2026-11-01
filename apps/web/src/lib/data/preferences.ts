import "server-only";

import { redirect } from "next/navigation";

import { createSupabaseServerClient } from "@/lib/supabase/server";

export type PreferencesDTO = {
  targetTitles: string[];
  careerLevels: string[];
  employmentTypes: string[];
  locations: string[];
  workplaceTypes: string[];
  sponsorshipPreference: string;
  includeKeywords: string[];
  excludeKeywords: string[];
  includeSeniorRoles: boolean;
  alertFrequency: string;
};

export type PreferencesData = {
  email: string | null;
  preferences: PreferencesDTO | null;
  loadError: string | null;
};
type Row = Record<string, unknown>;
const strings = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
const text = (value: unknown): string | null =>
  typeof value === "string" ? value : null;

export function mapPreferenceRow(value: unknown): PreferencesDTO | null {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    return null;
  const row = value as Row;
  const sponsorshipPreference = text(row.sponsorship_preference);
  const alertFrequency = text(row.alert_frequency);
  if (
    !sponsorshipPreference ||
    !alertFrequency ||
    typeof row.include_senior_roles !== "boolean"
  )
    return null;
  return {
    targetTitles: strings(row.target_titles),
    careerLevels: strings(row.career_levels),
    employmentTypes: strings(row.employment_types),
    locations: strings(row.locations),
    workplaceTypes: strings(row.workplace_types),
    sponsorshipPreference,
    includeKeywords: strings(row.include_keywords),
    excludeKeywords: strings(row.exclude_keywords),
    includeSeniorRoles: row.include_senior_roles,
    alertFrequency,
  };
}

export async function getPreferencesData(): Promise<PreferencesData> {
  const supabase = await createSupabaseServerClient();
  const { data: claimsData, error: claimsError } =
    await supabase.auth.getClaims();
  if (claimsError || typeof claimsData?.claims?.sub !== "string")
    redirect("/login");
  const { data, error } = await supabase
    .from("user_preferences")
    .select(
      "target_titles,career_levels,employment_types,locations,workplace_types,sponsorship_preference,include_keywords,exclude_keywords,include_senior_roles,alert_frequency",
    )
    .maybeSingle();
  return {
    email: text(claimsData.claims.email),
    preferences: error ? null : mapPreferenceRow(data),
    loadError:
      error || !data
        ? "Your preferences could not be loaded. Refresh to try again."
        : null,
  };
}
