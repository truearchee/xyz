import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Modal } from "./Modal";

describe("Modal — static a11y (§6.4)", () => {
  it("renders a dialog labelled by its heading when open", () => {
    render(
      <Modal isOpen onOpenChange={() => {}} title="Confirm delete">
        Body content
      </Modal>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeTruthy();
    // Labelled by the title heading (React Aria wires aria-labelledby from the slot="title" Heading).
    expect(screen.getByRole("heading", { name: "Confirm delete" })).toBeTruthy();
  });

  it("uses role=alertdialog for the destructive confirm variant", () => {
    render(
      <Modal isOpen onOpenChange={() => {}} title="Delete?" variant="confirm">
        Are you sure?
      </Modal>,
    );
    expect(screen.getByRole("alertdialog")).toBeTruthy();
  });
});
