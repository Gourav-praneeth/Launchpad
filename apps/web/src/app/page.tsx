import Link from "next/link";

const foundationChecks = [
  {
    title: "Database",
    detail:
      "Migrations define ownership, RLS, source checks, and immutable discovery time.",
    state: "Ready to apply",
  },
  {
    title: "Discovery worker",
    detail:
      "Typed configuration and structured logging are ready for the first source adapter.",
    state: "Foundation ready",
  },
  {
    title: "Web access",
    detail:
      "Browser and server Supabase clients use separate credential boundaries.",
    state: "Auth ready",
  },
] as const;

export default function Home() {
  return (
    <main className="app-shell">
      <header className="mobile-bar">
        <span className="brand-mark" aria-hidden="true">
          L
        </span>
        <span>Launchpad</span>
      </header>

      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            L
          </span>
          <span>Launchpad</span>
        </div>
        <nav>
          <Link className="nav-link active" href="/" aria-current="page">
            Foundation
          </Link>
        </nav>
        <p className="sidebar-note">Personal workspace</p>
      </aside>

      <section className="canvas" aria-labelledby="page-title">
        <div className="title-row">
          <div>
            <h1 id="page-title">Launchpad is ready for its first source.</h1>
            <p>
              The foundation keeps discovery timestamps honest, access private,
              and future alerts duplicate-safe.
            </p>
          </div>
          <a className="primary-action" href="#local-setup">
            Review local setup
          </a>
        </div>

        <section className="metric-strip" aria-label="Current data totals">
          <div>
            <span>Monitored sources</span>
            <strong>0</strong>
            <small>Added in Phase 2</small>
          </div>
          <div>
            <span>Discovered jobs</span>
            <strong>0</strong>
            <small>No sample jobs invented</small>
          </div>
          <div>
            <span>Duplicate alerts</span>
            <strong>0</strong>
            <small>Database constraint ready</small>
          </div>
          <div>
            <span>Last source check</span>
            <strong className="missing">—</strong>
            <small>No source has run</small>
          </div>
        </section>

        <section className="foundation-panel" id="local-setup">
          <div className="panel-heading">
            <div>
              <h2>Foundation status</h2>
              <p>
                Complete the local Supabase connection before adapter work
                begins.
              </p>
            </div>
            <span className="status-chip">Foundation</span>
          </div>
          <div className="check-list">
            {foundationChecks.map((check) => (
              <article key={check.title}>
                <div>
                  <h3>{check.title}</h3>
                  <p>{check.detail}</p>
                </div>
                <span>{check.state}</span>
              </article>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}
