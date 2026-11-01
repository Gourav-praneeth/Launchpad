"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import {
  initialWorkflowActionState,
  updateJobWorkflow,
} from "@/lib/jobs/actions";
import type { WorkflowStatus } from "@/lib/jobs/workflow";

type WorkflowButtonProps = {
  actionStatus: WorkflowStatus;
  className?: string;
  label: string;
  pendingLabel: string;
  pressed?: boolean;
};

function WorkflowButton({
  actionStatus,
  className,
  label,
  pendingLabel,
  pressed,
}: WorkflowButtonProps) {
  const { data, pending } = useFormStatus();
  const isThisAction = pending && data?.get("status") === actionStatus;

  return (
    <button
      className={className}
      type="submit"
      name="status"
      value={actionStatus}
      disabled={pending}
      aria-pressed={pressed}
    >
      {isThisAction ? pendingLabel : label}
    </button>
  );
}

type JobWorkflowControlsProps = {
  jobId: string;
  status: string | null;
};

export function JobWorkflowControls({
  jobId,
  status,
}: JobWorkflowControlsProps) {
  const [state, formAction] = useActionState(
    updateJobWorkflow,
    initialWorkflowActionState,
  );
  const isSaved = status === "saved";
  const isApplied = status === "applied";

  if (isApplied) {
    return <p className="workflow-complete">Application recorded</p>;
  }

  return (
    <form className="workflow-controls" action={formAction}>
      <input type="hidden" name="jobId" value={jobId} />
      <div>
        <WorkflowButton
          actionStatus={isSaved ? "new" : "saved"}
          label={isSaved ? "Saved" : "Save"}
          pendingLabel={isSaved ? "Removing…" : "Saving…"}
          pressed={isSaved}
        />
        <WorkflowButton
          actionStatus="applied"
          label="Mark applied"
          pendingLabel="Recording…"
        />
        <WorkflowButton
          actionStatus="not_interested"
          className="dismiss-action"
          label="Dismiss"
          pendingLabel="Dismissing…"
        />
      </div>
      {state.error ? (
        <p className="workflow-error" role="status">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}
