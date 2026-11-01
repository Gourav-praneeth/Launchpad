export type CompanyActionState = {
  error: string | null;
  success: string | null;
};

export const initialCompanyActionState: CompanyActionState = {
  error: null,
  success: null,
};

export type NewCompanyInput = {
  name: string;
  careersUrl: string;
  sourceUrl: string;
  checkIntervalMinutes: number;
};

type ParseResult<T> = { ok: true; value: T } | { ok: false; error: string };

const greenhousePattern =
  /^https:\/\/boards-api\.greenhouse\.io\/v1\/boards\/[A-Za-z0-9_-]+\/jobs\/?$/;
const allowedIntervals = new Set([15, 30, 60, 180, 360]);
const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const httpsUrl = (value: string): boolean => {
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
};

export function parseNewCompany(
  formData: FormData,
): ParseResult<NewCompanyInput> {
  const name = String(formData.get("name") ?? "").trim();
  const careersUrl = String(formData.get("careersUrl") ?? "").trim();
  const sourceUrl = String(formData.get("sourceUrl") ?? "").trim();
  const checkIntervalMinutes = Number(formData.get("checkIntervalMinutes"));

  if (!name || name.length > 120) {
    return { ok: false, error: "Enter a company name under 120 characters." };
  }
  if (!httpsUrl(careersUrl)) {
    return { ok: false, error: "Enter the company’s HTTPS careers URL." };
  }
  if (!greenhousePattern.test(sourceUrl)) {
    return {
      ok: false,
      error: "Enter the official Greenhouse list-jobs API URL.",
    };
  }
  if (!allowedIntervals.has(checkIntervalMinutes)) {
    return { ok: false, error: "Select a supported monitoring interval." };
  }
  return {
    ok: true,
    value: { name, careersUrl, sourceUrl, checkIntervalMinutes },
  };
}

export function parseMonitoringChange(
  formData: FormData,
): ParseResult<{ companyId: string; active: boolean }> {
  const companyId = String(formData.get("companyId") ?? "");
  const active = formData.get("active");
  if (!uuidPattern.test(companyId)) {
    return { ok: false, error: "The selected company is invalid." };
  }
  if (active !== "true" && active !== "false") {
    return { ok: false, error: "The monitoring state is invalid." };
  }
  return { ok: true, value: { companyId, active: active === "true" } };
}
