"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import {
  addWatchlistCompany,
  changeCompanyMonitoring,
} from "@/lib/companies/actions";
import { initialCompanyActionState } from "@/lib/companies/input";

function SubmitButton({
  children,
  pendingLabel,
  className = "primary-button",
}: {
  children: React.ReactNode;
  pendingLabel: string;
  className?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button className={className} type="submit" disabled={pending}>
      {pending ? pendingLabel : children}
    </button>
  );
}

export function AddCompanyForm() {
  const [state, action] = useActionState(
    addWatchlistCompany,
    initialCompanyActionState,
  );
  return (
    <form className="watchlist-form" action={action}>
      <div className="field-grid">
        <label>
          Company name
          <input
            name="name"
            required
            maxLength={120}
            autoComplete="organization"
          />
        </label>
        <label>
          Careers page
          <input
            name="careersUrl"
            type="url"
            required
            placeholder="https://company.com/careers"
          />
        </label>
      </div>
      <label>
        Greenhouse list-jobs API URL
        <input
          name="sourceUrl"
          type="url"
          required
          placeholder="https://boards-api.greenhouse.io/v1/boards/company/jobs"
        />
      </label>
      <div className="form-footer">
        <label>
          Check cadence
          <select name="checkIntervalMinutes" defaultValue="60">
            <option value="15">Every 15 minutes</option>
            <option value="30">Every 30 minutes</option>
            <option value="60">Every hour</option>
            <option value="180">Every 3 hours</option>
            <option value="360">Every 6 hours</option>
          </select>
        </label>
        <SubmitButton pendingLabel="Adding…">Add company</SubmitButton>
      </div>
      <ActionNotice state={state} />
    </form>
  );
}

function ActionNotice({ state }: { state: typeof initialCompanyActionState }) {
  const message = state.error ?? state.success;
  return message ? (
    <p
      className={`inline-notice ${state.error ? "error" : "success"}`}
      role="status"
    >
      {message}
    </p>
  ) : null;
}

export function MonitoringForm({
  companyId,
  active,
}: {
  companyId: string;
  active: boolean;
}) {
  const [state, action] = useActionState(
    changeCompanyMonitoring,
    initialCompanyActionState,
  );
  return (
    <form className="monitoring-form" action={action}>
      <input type="hidden" name="companyId" value={companyId} />
      <input type="hidden" name="active" value={String(!active)} />
      <SubmitButton
        className="secondary-button compact-button"
        pendingLabel="Updating…"
      >
        {active ? "Pause" : "Resume"}
      </SubmitButton>
      <ActionNotice state={state} />
    </form>
  );
}
