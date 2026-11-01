import { describe, expect, it } from "vitest";

import { parsePreferences } from "./input";

const validForm = () => {
  const form = new FormData();
  form.set("targetTitles", "Software Engineer\nBackend Engineer");
  form.append("careerLevels", "new_grad");
  form.append("employmentTypes", "full-time");
  form.append("workplaceTypes", "remote");
  form.set("locations", "Remote\nSeattle, WA");
  form.set("sponsorshipPreference", "any");
  form.set("alertFrequency", "immediate");
  return form;
};

describe("explicit preference input", () => {
  it("normalizes text lists and supported choices", () => {
    const result = parsePreferences(validForm());
    expect(result).toMatchObject({
      ok: true,
      value: {
        targetTitles: ["Software Engineer", "Backend Engineer"],
        careerLevels: ["new_grad"],
        employmentTypes: ["full-time"],
        workplaceTypes: ["remote"],
      },
    });
  });

  it("requires at least one target title and career level", () => {
    const form = validForm();
    form.set("targetTitles", "");
    expect(parsePreferences(form)).toEqual({
      ok: false,
      error: "Add at least one target job title.",
    });
  });

  it("ignores unsupported checkbox values", () => {
    const form = validForm();
    form.delete("careerLevels");
    form.append("careerLevels", "executive");
    expect(parsePreferences(form)).toEqual({
      ok: false,
      error: "Select at least one career level.",
    });
  });
});
