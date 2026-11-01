"use server";

import "server-only";

import { revalidatePath } from "next/cache";

import {
  initialPreferenceActionState,
  parsePreferences,
  type PreferenceActionState,
} from "@/lib/preferences/input";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export async function updatePreferences(
  _previousState: PreferenceActionState,
  formData: FormData,
): Promise<PreferenceActionState> {
  const input = parsePreferences(formData);
  if (!input.ok) return { ...initialPreferenceActionState, error: input.error };
  const supabase = await createSupabaseServerClient();
  const { data: claimsData, error: claimsError } =
    await supabase.auth.getClaims();
  if (claimsError || typeof claimsData?.claims?.sub !== "string")
    return { error: "Your session expired. Sign in again.", success: null };

  const value = input.value;
  const { error } = await supabase.rpc("update_job_preferences", {
    preference_target_titles: value.targetTitles,
    preference_career_levels: value.careerLevels,
    preference_employment_types: value.employmentTypes,
    preference_locations: value.locations,
    preference_workplace_types: value.workplaceTypes,
    preference_sponsorship: value.sponsorshipPreference,
    preference_include_keywords: value.includeKeywords,
    preference_exclude_keywords: value.excludeKeywords,
    preference_include_senior_roles: value.includeSeniorRoles,
    preference_alert_frequency: value.alertFrequency,
  });
  if (error)
    return {
      error:
        "Preferences could not be saved. Review the selections and try again.",
      success: null,
    };
  revalidatePath("/preferences");
  revalidatePath("/");
  return {
    error: null,
    success:
      "Preferences saved. Existing matches were cleared for a fresh evaluation.",
  };
}
