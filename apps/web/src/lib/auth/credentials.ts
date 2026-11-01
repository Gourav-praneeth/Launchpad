export type Credentials = {
  email: string;
  password: string;
};

export type CredentialResult =
  { ok: true; value: Credentials } | { ok: false; error: string };

export function parseCredentials(formData: FormData): CredentialResult {
  const rawEmail = formData.get("email");
  const rawPassword = formData.get("password");
  if (typeof rawEmail !== "string" || typeof rawPassword !== "string") {
    return { ok: false, error: "Enter an email address and password." };
  }

  const email = rawEmail.trim().toLowerCase();
  if (!/^\S+@\S+\.\S+$/.test(email)) {
    return { ok: false, error: "Enter a valid email address." };
  }
  if (rawPassword.length < 8) {
    return { ok: false, error: "Password must be at least 8 characters." };
  }

  return { ok: true, value: { email, password: rawPassword } };
}
