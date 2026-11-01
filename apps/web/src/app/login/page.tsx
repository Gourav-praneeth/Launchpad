import { redirect } from "next/navigation";

import { signIn, signUp } from "@/lib/auth/actions";
import { createSupabaseServerClient } from "@/lib/supabase/server";

type LoginPageProps = {
  searchParams: Promise<{ error?: string; message?: string }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const supabase = await createSupabaseServerClient();
  const { data } = await supabase.auth.getClaims();
  if (data?.claims?.sub) {
    redirect("/");
  }
  const notice = await searchParams;

  return (
    <main className="login-shell">
      <section className="login-intro" aria-labelledby="login-title">
        <div className="brand login-brand">
          <span className="launch-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>Launchpad</span>
        </div>
        <div>
          <h1 id="login-title">Fresh jobs, without the guesswork.</h1>
          <p>
            Monitor the companies you care about and see exactly when each role
            was discovered and last verified.
          </p>
        </div>
        <dl className="login-principles">
          <div>
            <dt>Company-first</dt>
            <dd>Official career sources from your watchlist.</dd>
          </div>
          <div>
            <dt>Timestamp-honest</dt>
            <dd>Employer dates never replace Launchpad discovery time.</dd>
          </div>
          <div>
            <dt>Preference-based</dt>
            <dd>No resume upload, parsing, or candidate profiling.</dd>
          </div>
        </dl>
      </section>

      <section className="login-panel" aria-label="Account access">
        <div>
          <h2>Open your job feed</h2>
          <p>Use an existing account or create your personal workspace.</p>
        </div>
        {notice.error ? (
          <p className="form-notice error">{notice.error}</p>
        ) : null}
        {notice.message ? (
          <p className="form-notice success">{notice.message}</p>
        ) : null}
        <form className="login-form">
          <label htmlFor="email">Email address</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            minLength={8}
            required
          />
          <button className="primary-button" formAction={signIn}>
            Sign in
          </button>
          <button className="secondary-button" formAction={signUp}>
            Create account
          </button>
        </form>
        <p className="privacy-note">
          Account access protects your company watchlist and job workflow.
        </p>
      </section>
    </main>
  );
}
