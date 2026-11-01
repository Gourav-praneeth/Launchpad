import { AppShell } from "@/app/app-shell";
import { PreferencesForm } from "@/app/preferences/preferences-form";
import { getPreferencesData } from "@/lib/data/preferences";

export default async function PreferencesPage() {
  const data = await getPreferencesData();
  return (
    <AppShell email={data.email} section="preferences" title="Preferences">
      <div className="title-row management-title">
        <div>
          <h1>Job preferences</h1>
          <p>
            Control deterministic matching with explicit choices you can inspect
            and change.
          </p>
        </div>
      </div>
      {data.loadError || !data.preferences ? (
        <div className="feed-state error-state">
          <h2>Preferences unavailable</h2>
          <p>{data.loadError}</p>
        </div>
      ) : (
        <PreferencesForm preferences={data.preferences} />
      )}
    </AppShell>
  );
}
