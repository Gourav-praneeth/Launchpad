import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "./page";

describe("foundation home", () => {
  it("presents honest empty-state totals and the next setup action", () => {
    render(<Home />);

    expect(
      screen.getByRole("heading", {
        name: "Launchpad is ready for its first source.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Review local setup" }),
    ).toHaveAttribute("href", "#local-setup");
    expect(screen.getByText("No sample jobs invented")).toBeInTheDocument();
  });
});
