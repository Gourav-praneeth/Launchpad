import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("@/lib/supabase/server", () => ({
  createSupabaseServerClient: vi.fn(),
}));

import * as workflowActions from "./actions";

describe("job workflow server action module", () => {
  it("exports only async-callable server actions", () => {
    expect(Object.keys(workflowActions)).toEqual(["updateJobWorkflow"]);
    expect(typeof workflowActions.updateJobWorkflow).toBe("function");
  });
});
