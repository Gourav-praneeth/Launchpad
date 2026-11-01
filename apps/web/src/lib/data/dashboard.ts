import "server-only";

import { redirect } from "next/navigation";

import type { WorkflowStatus } from "@/lib/jobs/workflow";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type MatchReasonDTO = {
  code: string;
  message: string;
  evidence: string[];
};

export type JobFeedItemDTO = {
  id: string;
  title: string;
  company: string;
  location: string | null;
  workplaceType: string | null;
  employmentType: string | null;
  applyUrl: string;
  employerPostedAt: string | null;
  firstSeenAt: string;
  lastVerifiedAt: string | null;
  listingStatus: "open" | "closed" | "uncertain";
  matchStatus: "matched" | "review" | "rejected" | null;
  matchReasons: MatchReasonDTO[];
  workflowStatus:
    WorkflowStatus | "interviewing" | "rejected" | "closed" | null;
  savedAt: string | null;
  appliedAt: string | null;
};

export type DashboardData = {
  email: string | null;
  jobs: JobFeedItemDTO[];
  activeCompanies: number | null;
  lastSourceCheckAt: string | null;
  loadError: string | null;
  isTruncated: boolean;
};

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const stringOrNull = (value: unknown): string | null =>
  typeof value === "string" && value.length > 0 ? value : null;

const firstRecord = (value: unknown): UnknownRecord | null => {
  if (isRecord(value)) return value;
  if (Array.isArray(value) && isRecord(value[0])) return value[0];
  return null;
};

const parseReasons = (value: unknown): MatchReasonDTO[] => {
  if (!Array.isArray(value)) return [];
  return value.flatMap((reason) => {
    if (!isRecord(reason)) return [];
    const code = stringOrNull(reason.code);
    const message = stringOrNull(reason.message);
    if (!code || !message) return [];
    const evidence = Array.isArray(reason.evidence)
      ? reason.evidence.filter(
          (item): item is string => typeof item === "string",
        )
      : [];
    return [{ code, message, evidence }];
  });
};

export function mapJobRow(value: unknown): JobFeedItemDTO | null {
  if (!isRecord(value)) return null;
  const id = stringOrNull(value.id);
  const title = stringOrNull(value.title);
  const applyUrl = stringOrNull(value.apply_url);
  const firstSeenAt = stringOrNull(value.first_seen_at);
  const company = firstRecord(value.company);
  const companyName = company ? stringOrNull(company.name) : null;
  const rawListingStatus = stringOrNull(value.status);
  const listingStatus =
    rawListingStatus === "open" ||
    rawListingStatus === "closed" ||
    rawListingStatus === "uncertain"
      ? rawListingStatus
      : null;
  if (
    !id ||
    !title ||
    !applyUrl ||
    !firstSeenAt ||
    !companyName ||
    !listingStatus
  ) {
    return null;
  }

  const match = firstRecord(value.matches);
  const interaction = firstRecord(value.interactions);
  const rawMatchStatus = match ? stringOrNull(match.status) : null;
  const matchStatus =
    rawMatchStatus === "matched" ||
    rawMatchStatus === "review" ||
    rawMatchStatus === "rejected"
      ? rawMatchStatus
      : null;
  const rawWorkflowStatus = interaction
    ? stringOrNull(interaction.application_status)
    : null;
  const workflowStatus =
    rawWorkflowStatus === "new" ||
    rawWorkflowStatus === "saved" ||
    rawWorkflowStatus === "applied" ||
    rawWorkflowStatus === "interviewing" ||
    rawWorkflowStatus === "rejected" ||
    rawWorkflowStatus === "closed" ||
    rawWorkflowStatus === "not_interested"
      ? rawWorkflowStatus
      : null;

  return {
    id,
    title,
    company: companyName,
    location: stringOrNull(value.location),
    workplaceType: stringOrNull(value.workplace_type),
    employmentType: stringOrNull(value.employment_type),
    applyUrl,
    employerPostedAt: stringOrNull(value.employer_posted_at),
    firstSeenAt,
    lastVerifiedAt: stringOrNull(value.last_verified_at),
    listingStatus,
    matchStatus,
    matchReasons: parseReasons(match?.match_reasons),
    workflowStatus,
    savedAt: interaction ? stringOrNull(interaction.saved_at) : null,
    appliedAt: interaction ? stringOrNull(interaction.applied_at) : null,
  };
}

export async function getDashboardData(): Promise<DashboardData> {
  const supabase = await createSupabaseServerClient();
  const { data: claimsData, error: claimsError } =
    await supabase.auth.getClaims();
  const claims = claimsData?.claims;
  const userId = claims?.sub;
  if (claimsError || typeof userId !== "string") {
    redirect("/login");
  }
  const email = stringOrNull(claims?.email);

  const jobSelection = `id,title,location,workplace_type,employment_type,apply_url,
    employer_posted_at,first_seen_at,last_verified_at,status,
    company:companies!jobs_company_id_fkey(name),
    matches:job_matches!job_matches_job_id_fkey(status,match_reasons),
    interactions:user_jobs!user_jobs_job_id_fkey(application_status,saved_at,applied_at)`;
  const [jobsResult, companiesResult, sourceResult, workflowResult] =
    await Promise.all([
      supabase
        .from("jobs")
        .select(jobSelection)
        .eq("status", "open")
        .order("first_seen_at", { ascending: false })
        .limit(201),
      supabase
        .from("companies")
        .select("id", { count: "exact", head: true })
        .eq("is_active", true),
      supabase
        .from("sources")
        .select("last_attempt_at")
        .not("last_attempt_at", "is", null)
        .order("last_attempt_at", { ascending: false })
        .limit(1),
      supabase
        .from("user_jobs")
        .select("job_id")
        .in("application_status", ["saved", "applied"])
        .limit(501),
    ]);

  if (jobsResult.error) {
    return {
      email,
      jobs: [],
      activeCompanies: companiesResult.count,
      lastSourceCheckAt: null,
      loadError: "The job feed could not be loaded. Refresh to try again.",
      isTruncated: false,
    };
  }

  const freshRows = (jobsResult.data ?? []).slice(0, 200);
  const freshIds = new Set(
    freshRows.flatMap((row) => (typeof row.id === "string" ? [row.id] : [])),
  );
  const workflowJobIds = (workflowResult.data ?? [])
    .slice(0, 500)
    .flatMap((row) =>
      typeof row.job_id === "string" && !freshIds.has(row.job_id)
        ? [row.job_id]
        : [],
    );
  const workflowJobsResult =
    workflowJobIds.length > 0
      ? await supabase
          .from("jobs")
          .select(jobSelection)
          .in("id", workflowJobIds)
      : { data: [], error: null };
  const mappedJobs = [
    ...freshRows,
    ...(workflowJobsResult.error ? [] : (workflowJobsResult.data ?? [])),
  ].flatMap((row) => {
    const job = mapJobRow(row);
    return job ? [job] : [];
  });
  mappedJobs.sort(
    (left, right) =>
      new Date(right.firstSeenAt).getTime() -
      new Date(left.firstSeenAt).getTime(),
  );
  const source = firstRecord(sourceResult.data);

  return {
    email,
    jobs: mappedJobs,
    activeCompanies: companiesResult.error ? null : companiesResult.count,
    lastSourceCheckAt: source ? stringOrNull(source.last_attempt_at) : null,
    loadError: null,
    isTruncated:
      (jobsResult.data?.length ?? 0) > 200 ||
      (workflowResult.data?.length ?? 0) > 500,
  };
}
