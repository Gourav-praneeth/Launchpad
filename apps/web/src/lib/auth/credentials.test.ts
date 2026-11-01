import { describe, expect, it } from "vitest";

import { parseCredentials } from "./credentials";

const credentials = (email: string, password: string): FormData => {
  const formData = new FormData();
  formData.set("email", email);
  formData.set("password", password);
  return formData;
};

describe("credential parsing", () => {
  it("normalizes a valid email without changing the password", () => {
    expect(
      parseCredentials(
        credentials(" Graduate@Launchpad.test ", "password-123"),
      ),
    ).toEqual({
      ok: true,
      value: { email: "graduate@launchpad.test", password: "password-123" },
    });
  });

  it("rejects invalid emails and short passwords", () => {
    expect(
      parseCredentials(credentials("not-an-email", "password-123")),
    ).toEqual({
      ok: false,
      error: "Enter a valid email address.",
    });
    expect(
      parseCredentials(credentials("graduate@launchpad.test", "short")),
    ).toEqual({
      ok: false,
      error: "Password must be at least 8 characters.",
    });
  });
});
