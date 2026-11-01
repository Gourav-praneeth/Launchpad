import "server-only";

import { redirect } from "next/navigation";

import { createSupabaseServerClient } from "@/lib/supabase/server";

export type CompanySourceDTO = {
  id: string;
  sourceUrl: string;
  checkIntervalMinutes: number;
  lastAttemptAt: string | null;
  lastSuccessAt: string | null;
  lastError: string | null;
  consecutiveFailures: number;
  backoffUntil: string | null;
};

export type WatchlistCompanyDTO = {
  id: string;
  name: string;
  careersUrl: string;
  isActive: boolean;
  sources: CompanySourceDTO[];
};

export type CompaniesData = {
  email: string | null;
  companies: WatchlistCompanyDTO[];
  loadError: string | null;
};

type RecordValue = Record<string, unknown>;
const record = (value: unknown): value is RecordValue =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const stringValue = (value: unknown): string | null =>
  typeof value === "string" && value.length > 0 ? value : null;

export function mapCompanyRow(value: unknown): WatchlistCompanyDTO | null {
  if (!record(value)) return null;
  const id = stringValue(value.id);
  const name = stringValue(value.name);
  const careersUrl = stringValue(value.careers_url);
  if (!id || !name || !careersUrl || typeof value.is_active !== "boolean")
    return null;
  const sources = Array.isArray(value.sources)
    ? value.sources.flatMap((source) => {
        if (!record(source)) return [];
        const sourceId = stringValue(source.id);
        const sourceUrl = stringValue(source.source_url);
        if (
          !sourceId ||
          !sourceUrl ||
          typeof source.check_interval_minutes !== "number"
        )
          return [];
        return [
          {
            id: sourceId,
            sourceUrl,
            checkIntervalMinutes: source.check_interval_minutes,
            lastAttemptAt: stringValue(source.last_attempt_at),
            lastSuccessAt: stringValue(source.last_success_at),
            lastError: stringValue(source.last_error),
            consecutiveFailures:
              typeof source.consecutive_failures === "number"
                ? source.consecutive_failures
                : 0,
            backoffUntil: stringValue(source.backoff_until),
          },
        ];
      })
    : [];
  return { id, name, careersUrl, isActive: value.is_active, sources };
}

export async function getCompaniesData(): Promise<CompaniesData> {
  const supabase = await createSupabaseServerClient();
  const { data: claimsData, error: claimsError } =
    await supabase.auth.getClaims();
  if (claimsError || typeof claimsData?.claims?.sub !== "string")
    redirect("/login");
  const email = stringValue(claimsData.claims.email);
  const { data, error } = await supabase
    .from("companies")
    .select(
      "id,name,careers_url,is_active,sources(id,source_url,check_interval_minutes,last_attempt_at,last_success_at,last_error,consecutive_failures,backoff_until)",
    )
    .order("name");
  return {
    email,
    companies: error
      ? []
      : (data ?? []).flatMap((row) => {
          const company = mapCompanyRow(row);
          return company ? [company] : [];
        }),
    loadError: error
      ? "The watchlist could not be loaded. Refresh to try again."
      : null,
  };
}
