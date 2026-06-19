import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { StepProgress } from "./Progress";

describe("StepProgress — static a11y (§6.4)", () => {
  it("renders the FAILED step with explicit text, not color alone", () => {
    render(
      <StepProgress
        steps={[
          { label: "Embed", state: "completed" },
          { label: "Summarize", state: "failed" },
        ]}
      />,
    );
    // earlier step stays completed; failed step is labelled by explicit text
    expect(screen.getByText("Embed")).toBeTruthy();
    expect(screen.getByText("Done")).toBeTruthy();
    expect(screen.getByText("Summarize")).toBeTruthy();
    expect(screen.getByText("Failed")).toBeTruthy();
  });
});
