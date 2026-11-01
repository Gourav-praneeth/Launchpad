"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import type { PreferencesDTO } from "@/lib/data/preferences";
import { updatePreferences } from "@/lib/preferences/actions";
import {
  careerLevels,
  employmentTypes,
  initialPreferenceActionState,
  workplaceTypes,
} from "@/lib/preferences/input";

const labels: Record<string, string> = {
  new_grad: "New graduate",
  entry_level: "Entry level",
  early_career: "Early career",
  experienced: "Experienced",
  "full-time": "Full-time",
  "part-time": "Part-time",
  internship: "Internship",
  contract: "Contract",
  temporary: "Temporary",
  remote: "Remote",
  hybrid: "Hybrid",
  "on-site": "On-site",
};

function SaveButton() {
  const { pending } = useFormStatus();
  return (
    <button
      className="primary-button preferences-save"
      type="submit"
      disabled={pending}
    >
      {pending ? "Saving…" : "Save preferences"}
    </button>
  );
}

function CheckboxGroup({
  name,
  options,
  selected,
}: {
  name: string;
  options: readonly string[];
  selected: string[];
}) {
  return (
    <div className="choice-grid">
      {options.map((option) => (
        <label className="choice" key={option}>
          <input
            type="checkbox"
            name={name}
            value={option}
            defaultChecked={selected.includes(option)}
          />
          <span>{labels[option]}</span>
        </label>
      ))}
    </div>
  );
}

export function PreferencesForm({
  preferences,
}: {
  preferences: PreferencesDTO;
}) {
  const [state, action] = useActionState(
    updatePreferences,
    initialPreferenceActionState,
  );
  return (
    <form className="preferences-form" action={action}>
      <section className="management-section">
        <div className="section-intro">
          <h2>Role focus</h2>
          <p>
            Titles and levels define the roles Launchpad evaluates. Senior roles
            remain excluded unless you opt in.
          </p>
        </div>
        <div className="settings-panel form-stack">
          <label>
            Target titles
            <textarea
              name="targetTitles"
              rows={4}
              defaultValue={preferences.targetTitles.join("\n")}
              required
            />
            <small>
              One title per line, such as Software Engineer or Backend Engineer.
            </small>
          </label>
          <fieldset>
            <legend>Career levels</legend>
            <CheckboxGroup
              name="careerLevels"
              options={careerLevels}
              selected={preferences.careerLevels}
            />
          </fieldset>
          <label className="switch-choice">
            <input
              type="checkbox"
              name="includeSeniorRoles"
              value="true"
              defaultChecked={preferences.includeSeniorRoles}
            />
            <span>
              <strong>Include senior roles</strong>
              <small>Off by default to protect the new-graduate focus.</small>
            </span>
          </label>
        </div>
      </section>
      <section className="management-section">
        <div className="section-intro">
          <h2>Work preferences</h2>
          <p>
            Filter by employment type, workplace arrangement, and explicit
            location terms.
          </p>
        </div>
        <div className="settings-panel form-stack">
          <fieldset>
            <legend>Employment types</legend>
            <CheckboxGroup
              name="employmentTypes"
              options={employmentTypes}
              selected={preferences.employmentTypes}
            />
          </fieldset>
          <fieldset>
            <legend>Workplace types</legend>
            <CheckboxGroup
              name="workplaceTypes"
              options={workplaceTypes}
              selected={preferences.workplaceTypes}
            />
          </fieldset>
          <label>
            Locations
            <textarea
              name="locations"
              rows={3}
              defaultValue={preferences.locations.join("\n")}
            />
            <small>Leave empty to accept any location.</small>
          </label>
        </div>
      </section>
      <section className="management-section">
        <div className="section-intro">
          <h2>Listing signals</h2>
          <p>
            Use transparent listing metadata to include useful signals or reject
            known mismatches.
          </p>
        </div>
        <div className="settings-panel form-stack">
          <div className="field-grid">
            <label>
              Include keywords
              <textarea
                name="includeKeywords"
                rows={3}
                defaultValue={preferences.includeKeywords.join("\n")}
              />
            </label>
            <label>
              Exclude keywords
              <textarea
                name="excludeKeywords"
                rows={3}
                defaultValue={preferences.excludeKeywords.join("\n")}
              />
            </label>
          </div>
          <label>
            Sponsorship
            <select
              name="sponsorshipPreference"
              defaultValue={preferences.sponsorshipPreference}
            >
              <option value="any">Any / no filter</option>
              <option value="required">Sponsorship required</option>
              <option value="not_required">Sponsorship not required</option>
              <option value="unknown">Only unknown metadata</option>
            </select>
          </label>
        </div>
      </section>
      <section className="management-section">
        <div className="section-intro">
          <h2>Alerts</h2>
          <p>
            Choose when qualifying newly discovered roles should be grouped for
            delivery in Phase 5.
          </p>
        </div>
        <div className="settings-panel form-stack">
          <label>
            Alert frequency
            <select
              name="alertFrequency"
              defaultValue={preferences.alertFrequency}
            >
              <option value="immediate">Immediate</option>
              <option value="hourly_digest">Hourly digest</option>
              <option value="daily_digest">Daily digest</option>
            </select>
          </label>
          <p className="preference-preview">
            <strong>Match preview</strong>Launchpad will use only these explicit
            settings and employer listing metadata. No resume or candidate
            profile is stored.
          </p>
        </div>
      </section>
      <div className="save-bar">
        <div aria-live="polite">
          {state.error ? (
            <p className="inline-notice error">{state.error}</p>
          ) : state.success ? (
            <p className="inline-notice success">{state.success}</p>
          ) : (
            <p>
              Saving clears stale match results so the worker can evaluate them
              again.
            </p>
          )}
        </div>
        <SaveButton />
      </div>
    </form>
  );
}
