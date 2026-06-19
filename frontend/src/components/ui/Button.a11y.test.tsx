import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Button } from "./Button";

describe("Button — static a11y (§6.4)", () => {
  it("renders a real <button>", () => {
    render(<Button>Save</Button>);
    const btn = screen.getByRole("button", { name: "Save" });
    expect(btn.tagName).toBe("BUTTON");
  });

  it("sets aria-busy and disables (not color-only) when loading", () => {
    render(<Button isLoading>Save</Button>);
    const btn = screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
    expect(btn.getAttribute("aria-busy")).toBe("true");
    expect(btn.disabled).toBe(true);
  });
});
