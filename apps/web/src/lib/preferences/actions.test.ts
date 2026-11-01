import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("@/lib/supabase/server", () => ({
  createSupabaseServerClient: vi.fn(),
}));

describe("preference Server Action module", () => {
  it("exports only callable Server Actions", async () => {
    const exports = await import("./actions");
    expect(Object.keys(exports)).toEqual(["updatePreferences"]);
    expect(
      Object.values(exports).every((value) => typeof value === "function"),
    ).toBe(true);
  });
});
