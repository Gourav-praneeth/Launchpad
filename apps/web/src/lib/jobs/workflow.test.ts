import { describe, expect, it } from "vitest";

import { parseWorkflowMutation } from "./workflow";

describe("workflow mutation parsing", () => {
  it("accepts an explicit supported transition", () => {
    const formData = new FormData();
    formData.set("jobId", "40000000-0000-4000-8000-000000000001");
    formData.set("status", "saved");

    expect(parseWorkflowMutation(formData)).toEqual({
      ok: true,
      value: {
        jobId: "40000000-0000-4000-8000-000000000001",
        status: "saved",
      },
    });
  });

  it("rejects unknown statuses and malformed identifiers", () => {
    const formData = new FormData();
    formData.set("jobId", "not-a-job-id");
    formData.set("status", "interviewing");

    expect(parseWorkflowMutation(formData)).toEqual({
      ok: false,
      error: "The selected job is invalid.",
    });
  });
});
