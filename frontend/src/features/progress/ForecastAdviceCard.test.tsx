import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ForecastAdviceCard } from "./ForecastAdviceCard";

const mocks = vi.hoisted(() => ({
  getStudentForecastAdvice: vi.fn(),
}));

vi.mock("../../lib/api/wrapper", () => ({
  api: {
    analytics: {
      getStudentForecastAdvice: mocks.getStudentForecastAdvice,
    },
  },
}));

describe("Stage 11.6 ForecastAdviceCard", () => {
  beforeEach(() => {
    mocks.getStudentForecastAdvice.mockReset();
  });

  it("renders the deterministic template immediately, then swaps in AI text when ready", async () => {
    mocks.getStudentForecastAdvice
      .mockResolvedValueOnce({
        moduleId: "m1",
        forecastState: "at_risk",
        text: "TEMPLATE ADVICE TEXT",
        source: "template",
        aiStatus: "queued",
      })
      .mockResolvedValue({
        moduleId: "m1",
        forecastState: "at_risk",
        text: "AI ADVICE TEXT",
        source: "ai",
        aiStatus: "succeeded",
      });

    render(<ForecastAdviceCard moduleId="m1" />);

    // Deterministic/template text shows immediately, with a quiet pending affordance.
    expect(await screen.findByText("TEMPLATE ADVICE TEXT")).toBeTruthy();
    expect(screen.getByTestId("forecast-advice-pending")).toBeTruthy();
    expect(screen.getByTestId("forecast-advice-card").getAttribute("data-source")).toBe("template");

    // AI swaps in via the backoff poll.
    expect(await screen.findByText("AI ADVICE TEXT", {}, { timeout: 5000 })).toBeTruthy();
    expect(screen.queryByTestId("forecast-advice-pending")).toBeNull();
    expect(screen.getByTestId("forecast-advice-card").getAttribute("data-source")).toBe("ai");
  });

  it("keeps the template when AI is unavailable (template_fallback) and does not poll", async () => {
    mocks.getStudentForecastAdvice.mockResolvedValue({
      moduleId: "m1",
      forecastState: "at_risk",
      text: "TEMPLATE FALLBACK TEXT",
      source: "template",
      aiStatus: "template_fallback",
    });

    render(<ForecastAdviceCard moduleId="m1" />);

    expect(await screen.findByText("TEMPLATE FALLBACK TEXT")).toBeTruthy();
    expect(screen.queryByTestId("forecast-advice-pending")).toBeNull();
    expect(mocks.getStudentForecastAdvice).toHaveBeenCalledTimes(1); // terminal → no re-poll
  });

  it("renders the impossible-case advice tone-neutral (no danger styling)", async () => {
    mocks.getStudentForecastAdvice.mockResolvedValue({
      moduleId: "m1",
      forecastState: "impossible",
      text: "Aiming for B is your strongest goal from here — and you can revisit your target.",
      source: "ai",
      aiStatus: "succeeded",
    });

    render(<ForecastAdviceCard moduleId="m1" />);

    const card = await screen.findByTestId("forecast-advice-card");
    expect(card.getAttribute("data-forecast-state")).toBe("impossible");
    expect(screen.getByTestId("forecast-advice-text").textContent).toContain("Aiming for B");
    expect(card.className).not.toMatch(/danger|red|error|alarm/);
  });
});
