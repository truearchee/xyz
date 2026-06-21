import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ExamPrepStarters } from "./ExamPrepStarters";

// Stage 8.6b — exam-prep starters pre-fill the composer with exam-review prompts (distinct from the
// lecture/homework starters). Pure component.

describe("ExamPrepStarters", () => {
  it("renders the exam-prep starters scoped by data-testid", () => {
    render(<ExamPrepStarters scope="workspace" onPick={vi.fn()} />);
    expect(screen.getByTestId("workspace-examprep-starters")).toBeTruthy();
    expect(screen.getAllByTestId("workspace-examprep-starter").length).toBe(3);
  });

  it("pre-fills the composer on click", () => {
    const onPick = vi.fn();
    render(<ExamPrepStarters scope="workspace" onPick={onPick} />);
    fireEvent.click(screen.getAllByTestId("workspace-examprep-starter")[0]);
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(String(onPick.mock.calls[0][0]).length).toBeGreaterThan(0);
  });
});
