import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Input } from "./Input";

describe("Input — static a11y (§6.4)", () => {
  it("associates the label with the control", () => {
    render(<Input id="email" label="Email" />);
    const input = screen.getByLabelText("Email");
    expect(input.id).toBe("email");
  });

  it("wires the error via aria-describedby + aria-invalid + role=alert (not color-only)", () => {
    render(<Input id="email" label="Email" error="Required" />);
    const input = screen.getByLabelText("Email");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toContain("email-err");
    const alert = screen.getByRole("alert");
    expect(alert.id).toBe("email-err");
    expect(alert.textContent).toContain("Required");
  });
});
