export const careerLevels = [
  "new_grad",
  "entry_level",
  "early_career",
  "experienced",
] as const;
export const employmentTypes = [
  "full-time",
  "part-time",
  "internship",
  "contract",
  "temporary",
] as const;
export const workplaceTypes = ["remote", "hybrid", "on-site"] as const;
export const sponsorshipOptions = [
  "any",
  "required",
  "not_required",
  "unknown",
] as const;
export const alertFrequencies = [
  "immediate",
  "hourly_digest",
  "daily_digest",
] as const;

export type PreferenceActionState = {
  error: string | null;
  success: string | null;
};
export const initialPreferenceActionState: PreferenceActionState = {
  error: null,
  success: null,
};

export type PreferenceInput = {
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

type ParseResult =
  { ok: true; value: PreferenceInput } | { ok: false; error: string };

const list = (value: FormDataEntryValue | null): string[] => {
  if (typeof value !== "string") return [];
  return [
    ...new Set(
      value
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  ];
};

const selected = (
  formData: FormData,
  name: string,
  allowed: readonly string[],
): string[] =>
  formData
    .getAll(name)
    .flatMap((value) =>
      typeof value === "string" && allowed.includes(value) ? [value] : [],
    );

export function parsePreferences(formData: FormData): ParseResult {
  const targetTitles = list(formData.get("targetTitles"));
  const locations = list(formData.get("locations"));
  const includeKeywords = list(formData.get("includeKeywords"));
  const excludeKeywords = list(formData.get("excludeKeywords"));
  const chosenCareerLevels = selected(formData, "careerLevels", careerLevels);
  const chosenEmploymentTypes = selected(
    formData,
    "employmentTypes",
    employmentTypes,
  );
  const chosenWorkplaceTypes = selected(
    formData,
    "workplaceTypes",
    workplaceTypes,
  );
  const sponsorshipPreference = String(
    formData.get("sponsorshipPreference") ?? "",
  );
  const alertFrequency = String(formData.get("alertFrequency") ?? "");

  if (targetTitles.length === 0)
    return { ok: false, error: "Add at least one target job title." };
  if (chosenCareerLevels.length === 0)
    return { ok: false, error: "Select at least one career level." };
  if (!sponsorshipOptions.includes(sponsorshipPreference as never))
    return { ok: false, error: "Select a sponsorship preference." };
  if (!alertFrequencies.includes(alertFrequency as never))
    return { ok: false, error: "Select an alert frequency." };
  const allText = [
    ...targetTitles,
    ...locations,
    ...includeKeywords,
    ...excludeKeywords,
  ];
  if (allText.some((item) => item.length > 100) || allText.length > 100)
    return {
      ok: false,
      error:
        "Keep each preference under 100 characters and the form under 100 entries.",
    };

  return {
    ok: true,
    value: {
      targetTitles,
      careerLevels: chosenCareerLevels,
      employmentTypes: chosenEmploymentTypes,
      locations,
      workplaceTypes: chosenWorkplaceTypes,
      sponsorshipPreference,
      includeKeywords,
      excludeKeywords,
      includeSeniorRoles: formData.get("includeSeniorRoles") === "true",
      alertFrequency,
    },
  };
}
