import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DashboardData, JobFeedItemDTO } from "@/lib/data/dashboard";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth/actions", () => ({ signOut: vi.fn() }));
vi.mock("@/lib/data/dashboard", async () => {
  const actual = await vi.importActual<typeof import("@/lib/data/dashboard")>(
    "@/lib/data/dashboard",
  );
  return { ...actual, getDashboardData: vi.fn() };
});

import { DashboardView } from "./page";

const emptyDashboard = (): DashboardData => ({
  email: "graduate@launchpad.test",
  jobs: [],
  activeCompanies: 0,
  lastSourceCheckAt: null,
  loadError: null,
  isTruncated: false,
});

describe("freshness-first dashboard", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.useRealTimers();
  });

  it("keeps discovery, verification, and employer timestamps distinct", () => {
    const now = new Date();
    const data: DashboardData = {
      ...emptyDashboard(),
      activeCompanies: 1,
      lastSourceCheckAt: now.toISOString(),
      jobs: [
        {
          id: "job-1",
          title: "Software Engineer, New Grad",
          company: "Launchpad Fixture",
          location: "San Francisco, CA",
          workplaceType: "hybrid",
          employmentType: "full-time",
          applyUrl: "https://careers.example.test/jobs/1",
          employerPostedAt: null,
          firstSeenAt: now.toISOString(),
          lastVerifiedAt: now.toISOString(),
          matchStatus: "matched",
          matchReasons: [],
          workflowStatus: "new",
        },
      ],
    };

    render(<DashboardView data={data} />);

    expect(
      screen.getByRole("heading", { name: "Job feed" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Discovered")).toBeInTheDocument();
    expect(screen.getByText("Last verified")).toBeInTheDocument();
    expect(screen.getByText("Employer posted")).toBeInTheDocument();
    expect(screen.getByText("Not provided")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Apply on company site" }),
    ).toHaveAttribute("href", "https://careers.example.test/jobs/1");
  });

  it("shows an honest first-run state without invented jobs", () => {
    render(<DashboardView data={emptyDashboard()} />);

    expect(
      screen.getByRole("heading", { name: "No jobs discovered yet" }),
    ).toBeInTheDocument();
    expect(screen.getByText("No checks yet")).toBeInTheDocument();
    expect(screen.getByText("Companies watched")).toBeInTheDocument();
  });

  it("filters the review queue and excludes rejected jobs from the feed", () => {
    const now = new Date().toISOString();
    const baseJob: Omit<JobFeedItemDTO, "matchStatus"> = {
      id: "job-1",
      title: "Software Engineer, New Grad",
      company: "Launchpad Fixture",
      location: null,
      workplaceType: null,
      employmentType: "full-time",
      applyUrl: "https://careers.example.test/jobs/1",
      employerPostedAt: null,
      firstSeenAt: now,
      lastVerifiedAt: now,
      matchReasons: [],
      workflowStatus: null,
    };
    const data: DashboardData = {
      ...emptyDashboard(),
      jobs: [
        { ...baseJob, matchStatus: "review" },
        {
          ...baseJob,
          id: "job-2",
          title: "Senior Software Engineer",
          matchStatus: "rejected",
        },
      ],
    };

    render(<DashboardView data={data} view="review" />);

    expect(screen.getByText("Software Engineer, New Grad")).toBeInTheDocument();
    expect(
      screen.queryByText("Senior Software Engineer"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Review metadata")).toBeInTheDocument();
  });
});
