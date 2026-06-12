import { act } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ToastProvider, useToast } from "./Toast";

function Harness({ tone }: { tone: "info" | "error" }) {
  const { show } = useToast();
  return (
    <button type="button" onClick={() => show(tone, tone === "error" ? "Boom" : "Saved")}>
      fire
    </button>
  );
}

describe("Toast — static a11y (§6.4)", () => {
  it("renders a polite live region; error toasts do NOT auto-dismiss", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Harness tone="error" />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("fire"));

    // Live region present (the notifications region) + the error announced assertively.
    expect(screen.getByRole("region", { name: "Notifications" })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Boom");

    // Advance well past the auto-dismiss window — the error remains.
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(screen.queryByText("Boom")).not.toBeNull();
    vi.useRealTimers();
  });

  it("auto-dismisses non-error toasts", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Harness tone="info" />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("fire"));
    expect(screen.queryByText("Saved")).not.toBeNull();

    act(() => {
      vi.advanceTimersByTime(6_000);
    });
    expect(screen.queryByText("Saved")).toBeNull();
    vi.useRealTimers();
  });
});
