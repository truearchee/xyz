import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { HomeworkStarters } from "./HomeworkStarters";

// Stage 8.6a — the homework-mode starters pre-fill the composer with COACHING prompts. They are distinct
// from the lecture StarterChips (so homework reads as "bring your problem, get coached"). Pure component.

describe("HomeworkStarters", () => {
  it("renders the coaching starters scoped by data-testid", () => {
    render(<HomeworkStarters scope="workspace" onPick={vi.fn()} />);
    expect(screen.getByTestId("workspace-homework-starters")).toBeTruthy();
    expect(screen.getAllByTestId("workspace-homework-starter").length).toBe(3);
  });

  it("pre-fills the composer (calls onPick with the chip text) on click", () => {
    const onPick = vi.fn();
    render(<HomeworkStarters scope="workspace" onPick={onPick} />);
    const [first] = screen.getAllByTestId("workspace-homework-starter");
    fireEvent.click(first);
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(String(onPick.mock.calls[0][0]).length).toBeGreaterThan(0);
  });
});
