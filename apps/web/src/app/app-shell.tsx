import Link from "next/link";

import { signOut } from "@/lib/auth/actions";

type AppSection = "jobs" | "companies" | "preferences";

const destinations: { href: string; label: string; section: AppSection }[] = [
  { href: "/", label: "Job feed", section: "jobs" },
  { href: "/companies", label: "Companies", section: "companies" },
  { href: "/preferences", label: "Preferences", section: "preferences" },
];

function LaunchMark() {
  return (
    <span className="launch-mark" aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  );
}

type AppShellProps = {
  children: React.ReactNode;
  email: string | null;
  section: AppSection;
  title: string;
};

export function AppShell({ children, email, section, title }: AppShellProps) {
  return (
    <main className="app-shell">
      <header className="mobile-bar">
        <div>
          <LaunchMark />
          <span>{title}</span>
        </div>
        <nav aria-label="Mobile navigation">
          {destinations.map((destination) => (
            <Link
              className={destination.section === section ? "active" : undefined}
              href={destination.href}
              key={destination.section}
              aria-current={
                destination.section === section ? "page" : undefined
              }
            >
              {destination.label}
            </Link>
          ))}
        </nav>
      </header>

      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <LaunchMark />
          <span>Launchpad</span>
        </div>
        <p className="workspace-label">Personal workspace</p>
        <nav>
          {destinations.map((destination) => (
            <Link
              className={`nav-link${destination.section === section ? " active" : ""}`}
              href={destination.href}
              key={destination.section}
              aria-current={
                destination.section === section ? "page" : undefined
              }
            >
              {destination.label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-account">
          <span title={email ?? undefined}>{email ?? "Signed in"}</span>
          <form action={signOut}>
            <button type="submit">Sign out</button>
          </form>
        </div>
      </aside>

      <section className="canvas">{children}</section>
    </main>
  );
}
