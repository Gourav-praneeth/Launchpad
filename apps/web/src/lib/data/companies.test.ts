import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { mapCompanyRow } from "./companies";

describe("company source health mapping", () => {
  it("keeps retry health separate from successful-check freshness", () => {
    const company = mapCompanyRow({
      id: "20000000-0000-0000-0000-000000000001",
      name: "Launchpad Fixture",
      careers_url: "https://example.test/careers",
      is_active: true,
      sources: [
        {
          id: "30000000-0000-0000-0000-000000000001",
          source_url: "https://boards-api.greenhouse.io/v1/boards/fixture/jobs",
          check_interval_minutes: 60,
          last_attempt_at: "2026-11-01T10:00:00Z",
          last_success_at: "2026-11-01T09:00:00Z",
          last_error: "Fixture timeout",
          consecutive_failures: 2,
          backoff_until: "2026-11-01T10:10:00Z",
        },
      ],
    });

    expect(company?.sources[0]).toMatchObject({
      lastAttemptAt: "2026-11-01T10:00:00Z",
      lastSuccessAt: "2026-11-01T09:00:00Z",
      lastError: "Fixture timeout",
      consecutiveFailures: 2,
      backoffUntil: "2026-11-01T10:10:00Z",
    });
  });
});
