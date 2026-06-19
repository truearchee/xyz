import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Badge } from "./Badge";

describe("Badge — static a11y (§6.4)", () => {
  it("conveys status by a visible TEXT label, not color alone", () => {
    render(<Badge tone="danger">Failed</Badge>);
    expect(screen.getByText("Failed")).toBeTruthy();
  });
});
