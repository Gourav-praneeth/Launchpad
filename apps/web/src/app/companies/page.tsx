import { AppShell } from "@/app/app-shell";
import { LocalTime } from "@/app/local-time";
import { AddCompanyForm, MonitoringForm } from "@/app/companies/company-forms";
import { getCompaniesData } from "@/lib/data/companies";

export default async function CompaniesPage() {
  const data = await getCompaniesData();
  const activeCount = data.companies.filter(
    (company) => company.isActive,
  ).length;
  const pausedCount = data.companies.length - activeCount;
  return (
    <AppShell email={data.email} section="companies" title="Companies">
      <div className="title-row management-title">
        <div>
          <h1>Company watchlist</h1>
          <p>
            {activeCount} monitored · {pausedCount} paused. Only configured
            official sources are checked.
          </p>
        </div>
      </div>

      <section
        className="management-section split-management"
        aria-labelledby="add-company-heading"
      >
        <div className="section-intro">
          <h2 id="add-company-heading">Add a Greenhouse source</h2>
          <p>
            Use the employer’s official careers page and Greenhouse API
            endpoint. Other ATS adapters will be added independently.
          </p>
        </div>
        <div className="settings-panel">
          <AddCompanyForm />
        </div>
      </section>

      <section className="watchlist-panel" aria-labelledby="watchlist-heading">
        <div className="panel-heading">
          <div>
            <h2 id="watchlist-heading">Monitored companies</h2>
            <p>
              Pausing stops future checks without deleting jobs or freshness
              history.
            </p>
          </div>
          <span className="num">{data.companies.length}</span>
        </div>
        {data.loadError ? (
          <p className="list-state error-text">{data.loadError}</p>
        ) : data.companies.length === 0 ? (
          <p className="list-state">
            No companies yet. Add the first official Greenhouse source above.
          </p>
        ) : (
          <div className="company-list">
            {data.companies.map((company) => {
              const source = company.sources[0];
              return (
                <article className="company-row" key={company.id}>
                  <div className="company-identity">
                    <div>
                      <h3>{company.name}</h3>
                      <a
                        href={company.careersUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Careers page
                      </a>
                    </div>
                    <span
                      className={`status-mark ${company.isActive ? "active" : "paused"}`}
                    >
                      {company.isActive ? "Monitoring" : "Paused"}
                    </span>
                  </div>
                  <div className="source-detail">
                    <span>
                      Greenhouse · every{" "}
                      {source ? source.checkIntervalMinutes : "—"} min
                    </span>
                    <code title={source?.sourceUrl}>
                      {source?.sourceUrl ?? "Source unavailable"}
                    </code>
                  </div>
                  <dl className="source-health">
                    <div>
                      <dt>Last success</dt>
                      <dd>
                        {source?.lastSuccessAt ? (
                          <LocalTime value={source.lastSuccessAt} relative />
                        ) : (
                          "No successful check"
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>Last attempt</dt>
                      <dd>
                        {source?.lastAttemptAt ? (
                          <LocalTime value={source.lastAttemptAt} relative />
                        ) : (
                          "Not checked yet"
                        )}
                      </dd>
                    </div>
                  </dl>
                  <MonitoringForm
                    companyId={company.id}
                    active={company.isActive}
                  />
                </article>
              );
            })}
          </div>
        )}
      </section>
    </AppShell>
  );
}
