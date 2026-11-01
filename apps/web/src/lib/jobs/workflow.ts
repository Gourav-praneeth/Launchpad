export const workflowStatuses = [
  "new",
  "saved",
  "applied",
  "not_interested",
] as const;

export type WorkflowStatus = (typeof workflowStatuses)[number];

export type WorkflowMutation = {
  jobId: string;
  status: WorkflowStatus;
};

export type WorkflowMutationResult =
  { ok: true; value: WorkflowMutation } | { ok: false; error: string };

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function parseWorkflowMutation(
  formData: FormData,
): WorkflowMutationResult {
  const jobId = formData.get("jobId");
  const status = formData.get("status");
  if (typeof jobId !== "string" || !uuidPattern.test(jobId)) {
    return { ok: false, error: "The selected job is invalid." };
  }
  if (
    typeof status !== "string" ||
    !workflowStatuses.includes(status as WorkflowStatus)
  ) {
    return { ok: false, error: "The requested job status is invalid." };
  }
  return { ok: true, value: { jobId, status: status as WorkflowStatus } };
}
