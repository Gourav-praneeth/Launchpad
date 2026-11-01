import { describe, expect, it } from "vitest";

import { parseMonitoringChange, parseNewCompany } from "./input";

describe("company watchlist input", () => {
  it("accepts the official Greenhouse endpoint shape", () => {
    const form = new FormData();
    form.set("name", "Example Systems");
    form.set("careersUrl", "https://example.test/careers");
    form.set(
      "sourceUrl",
      "https://boards-api.greenhouse.io/v1/boards/example/jobs",
    );
    form.set("checkIntervalMinutes", "30");
    expect(parseNewCompany(form)).toEqual({
      ok: true,
      value: {
        name: "Example Systems",
        careersUrl: "https://example.test/careers",
        sourceUrl: "https://boards-api.greenhouse.io/v1/boards/example/jobs",
        checkIntervalMinutes: 30,
      },
    });
  });

  it("rejects unsupported feeds before calling the database", () => {
    const form = new FormData();
    form.set("name", "Example Systems");
    form.set("careersUrl", "https://example.test/careers");
    form.set("sourceUrl", "https://jobs.example.test/feed");
    form.set("checkIntervalMinutes", "60");
    expect(parseNewCompany(form)).toMatchObject({ ok: false });
  });

  it("validates monitoring targets and boolean state", () => {
    const form = new FormData();
    form.set("companyId", "20000000-0000-4000-8000-000000000001");
    form.set("active", "false");
    expect(parseMonitoringChange(form)).toEqual({
      ok: true,
      value: {
        companyId: "20000000-0000-4000-8000-000000000001",
        active: false,
      },
    });
  });

  it("accepts PostgreSQL UUIDs without requiring RFC version bits", () => {
    const form = new FormData();
    form.set("companyId", "29000000-0000-0000-0000-000000000001");
    form.set("active", "true");
    expect(parseMonitoringChange(form)).toMatchObject({ ok: true });
  });
});
