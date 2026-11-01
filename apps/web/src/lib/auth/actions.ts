"use server";

import "server-only";

import { redirect } from "next/navigation";

import { parseCredentials } from "@/lib/auth/credentials";
import { createSupabaseServerClient } from "@/lib/supabase/server";

const loginRedirect = (kind: "error" | "message", value: string): never => {
  redirect(`/login?${kind}=${encodeURIComponent(value)}`);
};

export async function signIn(formData: FormData) {
  const parsed = parseCredentials(formData);
  if (parsed.ok === false) {
    return loginRedirect("error", parsed.error);
  }

  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.signInWithPassword(parsed.value);
  if (error) {
    loginRedirect("error", "Email or password was not recognized.");
  }
  redirect("/");
}

export async function signUp(formData: FormData) {
  const parsed = parseCredentials(formData);
  if (parsed.ok === false) {
    return loginRedirect("error", parsed.error);
  }

  const supabase = await createSupabaseServerClient();
  const { data, error } = await supabase.auth.signUp(parsed.value);
  if (error) {
    loginRedirect("error", "The account could not be created.");
  }
  if (!data.session) {
    loginRedirect(
      "message",
      "Check your email to finish creating the account.",
    );
  }
  redirect("/");
}

export async function signOut() {
  const supabase = await createSupabaseServerClient();
  await supabase.auth.signOut();
  redirect("/login");
}
