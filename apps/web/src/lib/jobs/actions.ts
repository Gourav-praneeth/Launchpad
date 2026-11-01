"use server";

import "server-only";

import { revalidatePath } from "next/cache";

import {
  parseWorkflowMutation,
  type WorkflowStatus,
} from "@/lib/jobs/workflow";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export type WorkflowActionState = {
  error: string | null;
  updatedJobId: string | null;
  status: WorkflowStatus | null;
};

export const initialWorkflowActionState: WorkflowActionState = {
  error: null,
  updatedJobId: null,
  status: null,
};

export async function updateJobWorkflow(
  _previousState: WorkflowActionState,
  formData: FormData,
): Promise<WorkflowActionState> {
  const mutation = parseWorkflowMutation(formData);
  if (!mutation.ok) {
    return { ...initialWorkflowActionState, error: mutation.error };
  }

  const supabase = await createSupabaseServerClient();
  const { data: claimsData, error: claimsError } =
    await supabase.auth.getClaims();
  if (claimsError || typeof claimsData?.claims?.sub !== "string") {
    return {
      ...initialWorkflowActionState,
      error: "Your session expired. Sign in again before updating this job.",
    };
  }

  const { error } = await supabase.rpc("set_job_workflow_status", {
    target_job_id: mutation.value.jobId,
    target_status: mutation.value.status,
  });
  if (error) {
    return {
      ...initialWorkflowActionState,
      error: "This job could not be updated. Refresh and try again.",
    };
  }

  revalidatePath("/");
  return {
    error: null,
    updatedJobId: mutation.value.jobId,
    status: mutation.value.status,
  };
}
