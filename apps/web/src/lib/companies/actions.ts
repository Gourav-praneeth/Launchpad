"use server";

import "server-only";

import { revalidatePath } from "next/cache";

import {
  initialCompanyActionState,
  parseMonitoringChange,
  parseNewCompany,
  type CompanyActionState,
} from "@/lib/companies/input";
import { createSupabaseServerClient } from "@/lib/supabase/server";

async function authenticatedClient() {
  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.getClaims();
  return error || typeof data?.claims?.sub !== "string" ? null : supabase;
}

export async function addWatchlistCompany(
  _previousState: CompanyActionState,
  formData: FormData,
): Promise<CompanyActionState> {
  const input = parseNewCompany(formData);
  if (!input.ok) return { ...initialCompanyActionState, error: input.error };
  const supabase = await authenticatedClient();
  if (!supabase)
    return { error: "Your session expired. Sign in again.", success: null };

  const { error } = await supabase.rpc("create_watchlist_company", {
    company_name: input.value.name,
    company_careers_url: input.value.careersUrl,
    greenhouse_source_url: input.value.sourceUrl,
    interval_minutes: input.value.checkIntervalMinutes,
  });
  if (error) {
    const duplicate = error.code === "23505";
    return {
      error: duplicate
        ? "That company or source is already on your watchlist."
        : "The company could not be added. Check the URLs and try again.",
      success: null,
    };
  }
  revalidatePath("/companies");
  revalidatePath("/");
  return { error: null, success: `${input.value.name} is now monitored.` };
}

export async function changeCompanyMonitoring(
  _previousState: CompanyActionState,
  formData: FormData,
): Promise<CompanyActionState> {
  const input = parseMonitoringChange(formData);
  if (!input.ok) return { ...initialCompanyActionState, error: input.error };
  const supabase = await authenticatedClient();
  if (!supabase)
    return { error: "Your session expired. Sign in again.", success: null };

  const { error } = await supabase.rpc("set_company_monitoring", {
    target_company_id: input.value.companyId,
    monitoring_active: input.value.active,
  });
  if (error)
    return {
      error: "Monitoring could not be updated. Refresh and try again.",
      success: null,
    };
  revalidatePath("/companies");
  revalidatePath("/");
  return {
    error: null,
    success: input.value.active ? "Monitoring resumed." : "Monitoring paused.",
  };
}
