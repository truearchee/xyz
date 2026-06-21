import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { GamificationPanel } from "./GamificationPanel";
import type { GamificationRead } from "../../lib/api";

// Stage 10 — runtime check of the panel's render logic (streak row, badge grid, status line, states).
// The api wrapper is mocked so this needs no backend/Supabase; the live event→streak→badge path is the
// browser gate's job. We assert state is carried by TEXT (not colour/icon alone), matching Stage 9 a11y.

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));
vi.mock("../../lib/api/wrapper", () => ({ api: { gamification: { get: getMock } } }));

const GLOBAL_SCOPE = "00000000-0000-0000-0000-000000000000";

function data(over: Partial<GamificationRead> = {}): GamificationRead {
  return {
    currentStreak: 3,
    longestStreak: 5,
    todayIsScheduled: true,
    todaySatisfied: true,
    nextScheduledDay: null,
    streakStatus: "active",
    earnedBadges: [],
    lockedBadges: [],
    progressItems: [],
    newBadgeIds: [],
    lastSeenAt: null,
    ...over,
  };
}

describe("GamificationPanel", () => {
  it("renders the streak and earned/locked badges with text-carried state", async () => {
    getMock.mockResolvedValueOnce(
      data({
        earnedBadges: [
          {
            badgeKey: "streak_3",
            family: "consistency",
            title: "3-day streak",
            description: "Learn on 3 scheduled class days in a row.",
            icon: "flame",
            scopeType: "global",
            scopeId: GLOBAL_SCOPE,
            earnedAt: "2026-06-20T00:00:00Z",
            qualifiedValue: 5,
            threshold: 3,
          },
        ],
        lockedBadges: [
          {
            badgeKey: "quizzes_10",
            family: "effort",
            title: "Ten quizzes",
            description: "Complete 10 different quizzes.",
            icon: "stack",
            scopeType: "global",
            scopeId: GLOBAL_SCOPE,
            current: 7,
            target: 10,
          },
        ],
        progressItems: [{ key: "quizzes", label: "Quizzes completed", current: 7, target: 10 }],
      }),
    );
    render(<GamificationPanel />);

    expect((await screen.findByTestId("streak-current")).textContent).toContain("3");
    expect(screen.getByTestId("streak-longest").textContent).toContain("5");
    // Status conveyed by visible TEXT (not colour/icon alone).
    expect(screen.getByTestId("streak-status").textContent?.length ?? 0).toBeGreaterThan(0);
    expect(screen.getByTestId("badge-earned-streak_3")).toBeTruthy();
    expect(within(screen.getByTestId("badge-earned-streak_3")).getByText("Earned")).toBeTruthy();
    // Locked badge shows progress as text "7/10", not opacity alone.
    expect(screen.getByTestId("badge-locked-quizzes_10").textContent).toContain("7/10");
  });

  it("shows the broken status and an empty state when there are no badges", async () => {
    getMock.mockResolvedValueOnce(
      data({ currentStreak: 0, streakStatus: "broken", earnedBadges: [], lockedBadges: [] }),
    );
    render(<GamificationPanel />);
    const status = await screen.findByTestId("streak-status");
    expect(status.getAttribute("data-status")).toBe("broken");
    expect(screen.getByText(/No badges yet/i)).toBeTruthy();
  });

  it("renders an error state without crashing when the fetch fails", async () => {
    getMock.mockRejectedValueOnce(new Error("boom"));
    render(<GamificationPanel />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    // The placeholder slot stays present so My Progress layout is unaffected.
    expect(screen.getByTestId("gamification-placeholder")).toBeTruthy();
  });
});
