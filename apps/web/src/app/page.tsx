import Link from "next/link";

import { LocalTime } from "@/app/local-time";
import { signOut } from "@/lib/auth/actions";
import {
  getDashboardData,
  type DashboardData,
  type JobFeedItemDTO,
} from "@/lib/data/dashboard";

type FeedView = "newest" | "matched" | "review";

type DashboardViewProps = {
  data: DashboardData;
  view?: FeedView;
};

const validView = (value: string | undefined): FeedView => {
  if (value === "matched" || value === "review") return value;
  return "newest";
};

const withinLastDay = (value: string): boolean =>
  new Date(value).getTime() >= Date.now() - 24 * 60 * 60 * 1000;

const displayValue = (value: number | null): string =>
  value === null ? "—" : new Intl.NumberFormat().format(value);

const sentenceCase = (value: string): string =>
  value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());

const jobMetadata = (job: JobFeedItemDTO): string =>
  [job.location, job.workplaceType, job.employmentType]
    .filter((value): value is string => Boolean(value))
    .join(" · ") || "Location and work arrangement unavailable";

function MatchLabel({ job }: { job: JobFeedItemDTO }) {
  if (job.matchStatus === "matched") {
    return <span className="match-label matched">Preference match</span>;
  }
  if (job.matchStatus === "review") {
    return <span className="match-label review">Review metadata</span>;
  }
  return <span className="match-label neutral">Not evaluated</span>;
}

function FreshnessTrail({ job }: { job: JobFeedItemDTO }) {
  return (
    <dl className="freshness-trail">
      <div className="primary-freshness">
        <dt>Discovered</dt>
        <dd>
          <LocalTime value={job.firstSeenAt} relative />
        </dd>
      </div>
      <div>
        <dt>Last verified</dt>
        <dd>
          {job.lastVerifiedAt ? (
            <LocalTime value={job.lastVerifiedAt} relative />
          ) : (
            "Not yet verified"
          )}
        </dd>
      </div>
      <div>
        <dt>Employer posted</dt>
        <dd>
          {job.employerPostedAt ? (
            <LocalTime value={job.employerPostedAt} />
          ) : (
            "Not provided"
          )}
        </dd>
      </div>
    </dl>
  );
}

export function DashboardView({ data, view = "newest" }: DashboardViewProps) {
  const eligibleJobs = data.jobs.filter(
    (job) => job.matchStatus !== "rejected",
  );
  const matchedCount = eligibleJobs.filter(
    (job) => job.matchStatus === "matched",
  ).length;
  const reviewCount = eligibleJobs.filter(
    (job) => job.matchStatus === "review",
  ).length;
  const newCount = eligibleJobs.filter((job) =>
    withinLastDay(job.firstSeenAt),
  ).length;
  const filteredJobs = eligibleJobs.filter((job) => {
    if (view === "matched") return job.matchStatus === "matched";
    if (view === "review") return job.matchStatus === "review";
    return true;
  });
  const finding =
    newCount === 0
      ? "No relevant roles were discovered in the last 24 hours."
      : `${newCount} relevant ${newCount === 1 ? "role was" : "roles were"} discovered in the last 24 hours.`;

  return (
    <main className="app-shell">
      <header className="mobile-bar">
        <span className="launch-mark" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span>Job feed</span>
      </header>

      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <span className="launch-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>Launchpad</span>
        </div>
        <p className="workspace-label">Personal workspace</p>
        <nav>
          <Link className="nav-link active" href="/" aria-current="page">
            Job feed
          </Link>
        </nav>
        <div className="sidebar-account">
          <span title={data.email ?? undefined}>
            {data.email ?? "Signed in"}
          </span>
          <form action={signOut}>
            <button type="submit">Sign out</button>
          </form>
        </div>
      </aside>

      <section className="canvas" aria-labelledby="page-title">
        <div className="title-row">
          <div>
            <h1 id="page-title">Job feed</h1>
            <p>{finding}</p>
          </div>
          <p className="source-freshness">
            Last source check
            <strong>
              {data.lastSourceCheckAt ? (
                <LocalTime value={data.lastSourceCheckAt} relative />
              ) : (
                "No checks yet"
              )}
            </strong>
          </p>
        </div>

        <section className="metric-strip" aria-label="Current job totals">
          <div>
            <span>New in 24 hours</span>
            <strong>{newCount}</strong>
          </div>
          <div>
            <span>Preference matches</span>
            <strong>{matchedCount}</strong>
          </div>
          <div>
            <span>Needs review</span>
            <strong>{reviewCount}</strong>
          </div>
          <div>
            <span>Companies watched</span>
            <strong>{displayValue(data.activeCompanies)}</strong>
          </div>
        </section>

        <section className="feed-panel" aria-labelledby="feed-heading">
          <div className="feed-heading">
            <div>
              <h2 id="feed-heading">Freshest relevant roles</h2>
              <p>Ordered by Launchpad discovery time, newest first.</p>
            </div>
            <nav className="feed-tabs" aria-label="Filter job feed">
              <Link
                className={view === "newest" ? "active" : undefined}
                href="/?view=newest"
                aria-current={view === "newest" ? "page" : undefined}
              >
                Newest
              </Link>
              <Link
                className={view === "matched" ? "active" : undefined}
                href="/?view=matched"
                aria-current={view === "matched" ? "page" : undefined}
              >
                Matches {matchedCount}
              </Link>
              <Link
                className={view === "review" ? "active" : undefined}
                href="/?view=review"
                aria-current={view === "review" ? "page" : undefined}
              >
                Review {reviewCount}
              </Link>
            </nav>
          </div>

          {data.loadError ? (
            <div className="feed-state error-state">
              <h3>Job feed unavailable</h3>
              <p>{data.loadError}</p>
            </div>
          ) : filteredJobs.length === 0 ? (
            <div className="feed-state">
              <h3>
                {data.jobs.length === 0
                  ? "No jobs discovered yet"
                  : "No jobs in this view"}
              </h3>
              <p>
                {data.jobs.length === 0
                  ? "Once a configured source runs successfully, new roles will appear here with separate discovery and verification times."
                  : "Try another filter or update your explicit job preferences."}
              </p>
            </div>
          ) : (
            <div className="job-list">
              {filteredJobs.slice(0, 50).map((job) => (
                <article className="job-row" key={job.id}>
                  <div className="job-summary">
                    <div className="job-company-line">
                      <span>{job.company}</span>
                      <MatchLabel job={job} />
                    </div>
                    <h3>{job.title}</h3>
                    <p>{jobMetadata(job)}</p>
                    {job.workflowStatus && job.workflowStatus !== "new" ? (
                      <p className="workflow-state">
                        Your status: {sentenceCase(job.workflowStatus)}
                      </p>
                    ) : null}
                  </div>
                  <FreshnessTrail job={job} />
                  <a
                    className="apply-link"
                    href={job.applyUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Apply on company site
                  </a>
                </article>
              ))}
            </div>
          )}
          {data.isTruncated ? (
            <p className="truncation-note">
              Showing the 200 freshest open jobs. Narrower filters are coming in
              the next dashboard increment.
            </p>
          ) : null}
        </section>
      </section>
    </main>
  );
}

type HomeProps = {
  searchParams: Promise<{ view?: string }>;
};

export default async function Home({ searchParams }: HomeProps) {
  const [data, parameters] = await Promise.all([
    getDashboardData(),
    searchParams,
  ]);
  return <DashboardView data={data} view={validView(parameters.view)} />;
}
