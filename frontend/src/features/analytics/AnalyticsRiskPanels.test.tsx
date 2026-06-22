import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LecturerAssessmentInsightsPanel } from "./LecturerAssessmentInsightsPanel";
import { LecturerRosterRiskPanel } from "./LecturerRosterRiskPanel";
import { StudentRiskCard } from "./StudentRiskCard";
import { StudentWorkloadPlanner } from "./StudentWorkloadPlanner";

const mocks = vi.hoisted(() => ({
  dismissLecturerRecommendation: vi.fn(),
  dismissStudentRecommendation: vi.fn(),
  getLecturerAssessmentInsights: vi.fn(),
  getLecturerRosterRisk: vi.fn(),
  getLecturerStudentRecommendations: vi.fn(),
  getStudentModuleRecommendations: vi.fn(),
  getStudentRisk: vi.fn(),
  getStudentWorkloadAvailability: vi.fn(),
  getStudentWorkloadPlan: vi.fn(),
  markLecturerRecommendationActed: vi.fn(),
  generateStudentWorkloadPlan: vi.fn(),
  updateStudentWorkloadAvailability: vi.fn(),
  downloadWorkloadPlanCalendar: vi.fn(),
}));

vi.mock("../../lib/api/wrapper", () => ({
  api: {
    analytics: {
      dismissLecturerRecommendation: mocks.dismissLecturerRecommendation,
      dismissStudentRecommendation: mocks.dismissStudentRecommendation,
      getLecturerAssessmentInsights: mocks.getLecturerAssessmentInsights,
      getLecturerRosterRisk: mocks.getLecturerRosterRisk,
      getLecturerStudentRecommendations: mocks.getLecturerStudentRecommendations,
      getStudentModuleRecommendations: mocks.getStudentModuleRecommendations,
      getStudentRisk: mocks.getStudentRisk,
      getStudentWorkloadAvailability: mocks.getStudentWorkloadAvailability,
      getStudentWorkloadPlan: mocks.getStudentWorkloadPlan,
      generateStudentWorkloadPlan: mocks.generateStudentWorkloadPlan,
      markLecturerRecommendationActed: mocks.markLecturerRecommendationActed,
      updateStudentWorkloadAvailability: mocks.updateStudentWorkloadAvailability,
      downloadWorkloadPlanCalendar: mocks.downloadWorkloadPlanCalendar,
    },
  },
}));

describe("Stage 11.1 analytics risk panels", () => {
  it("renders lecturer tier, reasons, and cited metrics", async () => {
    mocks.getLecturerRosterRisk.mockResolvedValueOnce({
      moduleId: "module-1",
      moduleTitle: "Finance",
      needsSupportCount: 1,
      rows: [
        {
          studentId: "student-1",
          studentName: "Ada Lovelace",
          studentEmail: "ada@example.test",
          moduleId: "module-1",
          riskTier: "needs_support",
          riskLabel: "Needs support",
          riskReasons: [
            {
              code: "missed_recent_quizzes",
              severity: "needs_support",
              metricKeys: ["missedRecentQuizCount", "recentQuizWindow"],
              lecturerText: "Missed 2 of the last 3 quiz opportunities",
              studentText: "Recent quiz practice could use a little time.",
              supportingMetrics: { missedRecentQuizCount: 2, recentQuizWindow: 3 },
            },
          ],
          algorithmVersion: "risk-v1",
          inputHash: "hash",
          sourceCutoffAt: "2026-06-20T06:00:00Z",
          computedAt: "2026-06-20T06:00:01Z",
        },
      ],
    });
    mocks.getLecturerStudentRecommendations.mockResolvedValueOnce({
      studentId: "student-1",
      studentName: "Ada Lovelace",
      studentEmail: "ada@example.test",
      moduleId: "module-1",
      moduleTitle: "Finance",
      riskReasons: [
        {
          code: "missed_recent_quizzes",
          severity: "needs_support",
          metricKeys: ["missedRecentQuizCount", "recentQuizWindow"],
          lecturerText: "Missed 2 of the last 3 quiz opportunities",
          studentText: "Recent quiz practice could use a little time.",
          supportingMetrics: { missedRecentQuizCount: 2, recentQuizWindow: 3 },
        },
      ],
      recommendations: [
        {
          id: "recommendation-1",
          reasonCode: "missed_recent_quizzes",
          targetKey: "module:module-1",
          targetLabel: "Module",
          lecturerState: "new",
          studentState: "new",
          aiStatus: "succeeded",
          lecturerDraftText: "Please check in about recent quiz practice.",
          lecturerDraftSource: "ai",
          studentNudgeText: "Recent quiz practice could use a little time.",
          studentNudgeSource: "ai",
          studentNextStep: "Review the latest quiz practice.",
          deterministicPayload: {},
          aiProvenance: null,
          createdAt: "2026-06-20T06:00:00Z",
          updatedAt: "2026-06-20T06:00:00Z",
        },
      ],
    });

    render(<LecturerRosterRiskPanel moduleId="module-1" />);

    await waitFor(() => expect(screen.getByTestId("needs-support-count").textContent).toBe("Needs support: 1"));
    const row = within(screen.getByTestId("lecturer-risk-row-student-1"));
    expect(row.getByText("Ada Lovelace")).toBeTruthy();
    expect(row.getByText("Needs support")).toBeTruthy();
    expect(row.getByText("Missed 2 of the last 3 quiz opportunities")).toBeTruthy();
    expect(row.getByText("missedRecentQuizCount: 2 · recentQuizWindow: 3")).toBeTruthy();

    fireEvent.click(row.getByRole("button", { name: "Review" }));
    await waitFor(() => expect(screen.getByTestId("lecturer-recommendation-modal")).toBeTruthy());
    const modal = within(screen.getByTestId("lecturer-recommendation-modal").closest("section")!);
    expect(modal.getByRole("button", { name: "Copy draft" })).toBeTruthy();
    expect(modal.getByRole("button", { name: "Mark acted" })).toBeTruthy();
    expect(modal.getByRole("button", { name: "Dismiss" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /send/i })).toBeNull();
  });

  it("renders student gentle copy without tier labels or peer language", async () => {
    mocks.getStudentRisk.mockResolvedValueOnce({
      studentId: "student-1",
      moduleId: "module-1",
      riskReasons: [
        {
          code: "topic_deadline_gap",
          studentText: "Derivatives could use a little extra time before the deadline.",
        },
      ],
      algorithmVersion: "risk-v1",
      inputHash: "hash",
      sourceCutoffAt: "2026-06-20T06:00:00Z",
      computedAt: "2026-06-20T06:00:01Z",
    });
    mocks.getStudentModuleRecommendations.mockResolvedValueOnce({
      recommendations: [
        {
          id: "recommendation-1",
          moduleId: "module-1",
          moduleTitle: "Finance",
          targetLabel: "Derivatives",
          text: "Derivatives is worth reviewing this week.",
          nextStep: "Review this topic before the upcoming deadline.",
          source: "ai",
          dismissible: true,
        },
      ],
    });

    render(<StudentRiskCard moduleId="module-1" />);

    await waitFor(() => expect(screen.getByTestId("student-risk-card")).toBeTruthy());
    expect(screen.getByText("Derivatives is worth reviewing this week.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Not now" })).toBeTruthy();
    expect(screen.queryByText("Needs support")).toBeNull();
    expect(screen.queryByText(/peer/i)).toBeNull();
    expect(screen.queryByText(/behind the class/i)).toBeNull();
  });
});

describe("Stage 11.3 assessment insights panel", () => {
  it("renders exact aggregate stats, ordered distractors, topic fallback, and small-cohort copy", async () => {
    mocks.getLecturerAssessmentInsights.mockResolvedValueOnce({
      moduleId: "module-1",
      moduleTitle: "Biology",
      latestAgentRun: null,
      smallCohortThreshold: 3,
      smallCohortMessage: "Not enough submissions for an aggregate insight",
      questions: [
        {
          questionKey: "q-dna",
          questionText: "Which phase copies DNA?",
          answerCount: 4,
          correctCount: 1,
          incorrectCount: 3,
          correctRatePercent: "25.00",
          smallCohort: false,
          smallCohortMessage: null,
          distractors: [
            {
              optionKey: "opt-m",
              optionText: "M phase",
              selectedCount: 2,
              selectedRatePercent: "50.00",
            },
            {
              optionKey: "opt-g1",
              optionText: "G1 phase",
              selectedCount: 1,
              selectedRatePercent: "25.00",
            },
          ],
        },
        {
          questionKey: "q-atp",
          questionText: "Which organelle makes ATP?",
          answerCount: 4,
          correctCount: 3,
          incorrectCount: 1,
          correctRatePercent: "75.00",
          smallCohort: false,
          smallCohortMessage: null,
          distractors: [
            {
              optionKey: "opt-ribo",
              optionText: "Ribosome",
              selectedCount: 1,
              selectedRatePercent: "25.00",
            },
          ],
        },
        {
          questionKey: "q-tiny",
          questionText: "Which label belongs to the unproven tiny cohort?",
          answerCount: 2,
          correctCount: 1,
          incorrectCount: 1,
          correctRatePercent: null,
          smallCohort: true,
          smallCohortMessage: "Not enough submissions for an aggregate insight",
          distractors: [
            {
              optionKey: "opt-beta",
              optionText: "Beta",
              selectedCount: 1,
              selectedRatePercent: null,
            },
          ],
        },
      ],
      mostMissedQuestions: [
        {
          questionKey: "q-dna",
          questionText: "Which phase copies DNA?",
          answerCount: 4,
          correctCount: 1,
          incorrectCount: 3,
          correctRatePercent: "25.00",
          smallCohort: false,
          smallCohortMessage: null,
          distractors: [],
        },
        {
          questionKey: "q-atp",
          questionText: "Which organelle makes ATP?",
          answerCount: 4,
          correctCount: 3,
          incorrectCount: 1,
          correctRatePercent: "75.00",
          smallCohort: false,
          smallCohortMessage: null,
          distractors: [],
        },
      ],
      topicMastery: {
        available: true,
        unavailableReason: null,
        unmappedAnswerCount: 2,
        unmappedMessage: "Topic mastery unavailable for 2 submissions without question provenance.",
        rows: [
          {
            sourceSectionId: "section-1",
            topicTitle: "Cell Division",
            weekNumber: 2,
            answerCount: 8,
            correctCount: 4,
            masteryPercent: "50.00",
            smallCohort: false,
            smallCohortMessage: null,
          },
        ],
      },
    });

    render(<LecturerAssessmentInsightsPanel moduleId="module-1" />);

    await waitFor(() => expect(screen.getByTestId("lecturer-assessment-insights")).toBeTruthy());
    expect(screen.getByTestId("assessment-question-count").textContent).toBe("Questions: 3");
    expect(screen.getByTestId("topic-mastery-unavailable").textContent).toBe(
      "Topic mastery unavailable for 2 submissions without question provenance.",
    );
    expect(screen.getByTestId("topic-mastery-percent-section-1").textContent).toBe("50.00%");

    const mostMissed = screen.getAllByTestId(/most-missed-/).map((node) => node.textContent);
    expect(mostMissed).toEqual([
      "Which phase copies DNA? · 3 missed · 25.00% correct",
      "Which organelle makes ATP? · 1 missed · 75.00% correct",
    ]);

    expect(screen.getByTestId("assessment-question-rate-q-dna").textContent).toBe("25.00%");
    expect(screen.getByTestId("assessment-question-rate-q-atp").textContent).toBe("75.00%");
    expect(screen.getByTestId("assessment-question-rate-q-tiny").textContent).toBe(
      "Not enough submissions for an aggregate insight",
    );
    const dnaDistractors = screen
      .getAllByTestId(/assessment-distractor-q-dna-/)
      .map((node) => node.textContent);
    expect(dnaDistractors).toEqual(["M phase: 2 (50.00%)", "G1 phase: 1 (25.00%)"]);
    expect(screen.getByTestId("assessment-distractor-q-tiny-opt-beta").textContent).toBe("Beta: 1");
  });
});

describe("Stage 11.4 workload planner", () => {
  it("renders availability controls and read-only stored plan items", async () => {
    const plan = {
      id: "plan-1",
      moduleId: "module-1",
      algorithmVersion: "workload-v1",
      inputHash: "hash-1",
      availabilityVersion: 1,
      sourceCutoffAt: "2026-06-20T08:00:00Z",
      isActive: true,
      supersededAt: null,
      provenance: {},
      createdAt: "2026-06-20T08:00:00Z",
      updatedAt: "2026-06-20T08:00:00Z",
      items: [
        {
          id: "item-1",
          taskKey: "deadline:one",
          sourceSectionId: "section-1",
          scheduledDate: "2026-06-22",
          window: "evening",
          scheduledStartAt: "2026-06-22T18:00:00Z",
          scheduledEndAt: "2026-06-22T19:30:00Z",
          label: "Prepare for Close assignment",
          estimateMinutes: 90,
          reason: "deadline",
          sourceReasonCode: null,
          sourceMetadata: {},
          tight: false,
          tightMessage: null,
          sortIndex: 0,
        },
        {
          id: "item-2",
          taskKey: "deadline:two",
          sourceSectionId: "section-2",
          scheduledDate: null,
          window: null,
          scheduledStartAt: null,
          scheduledEndAt: null,
          label: "Prepare for Tight lab",
          estimateMinutes: 45,
          reason: "deadline",
          sourceReasonCode: null,
          sourceMetadata: {},
          tight: true,
          tightMessage: "Plan may not fully fit before 2026-06-22.",
          sortIndex: 1,
        },
      ],
    };
    mocks.getStudentWorkloadAvailability.mockResolvedValueOnce({
      moduleId: "module-1",
      studyDays: ["monday", "wednesday"],
      preferredWindow: "evening",
      maxStudyMinutesPerDay: 90,
      availabilityVersion: 1,
      updatedAt: "2026-06-20T08:00:00Z",
    });
    mocks.getStudentWorkloadPlan.mockResolvedValueOnce(plan);
    mocks.updateStudentWorkloadAvailability.mockResolvedValueOnce({
      moduleId: "module-1",
      studyDays: ["monday", "wednesday"],
      preferredWindow: "evening",
      maxStudyMinutesPerDay: 90,
      availabilityVersion: 1,
      updatedAt: "2026-06-20T08:01:00Z",
    });
    mocks.generateStudentWorkloadPlan.mockResolvedValueOnce({
      ...plan,
      id: "plan-2",
      inputHash: "hash-2",
      updatedAt: "2026-06-20T08:01:00Z",
    });
    mocks.downloadWorkloadPlanCalendar.mockResolvedValueOnce({
      blob: new Blob(["BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"], { type: "text/calendar" }),
      fileName: "workload-plan.ics",
    });
    const createObjectURL = vi.fn(() => "blob:calendar");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(window.URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(window.URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    const clickAnchor = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const { container } = render(<StudentWorkloadPlanner moduleId="module-1" />);

    await waitFor(() => expect(screen.getByTestId("student-workload-planner")).toBeTruthy());
    expect(screen.getByTestId("workload-day-monday")).toHaveProperty("checked", true);
    expect(screen.getByTestId("workload-max-minutes")).toHaveProperty("value", "90");
    const firstItem = within(screen.getByTestId("workload-plan-item-0"));
    expect(firstItem.getByText("Prepare for Close assignment")).toBeTruthy();
    expect(screen.getByTestId("workload-plan-item-0").textContent).toContain("90 min");
    expect(screen.getByTestId("workload-plan-item-0").textContent).toContain("Deadline");
    expect(screen.getByTestId("workload-tight-1")).toBeTruthy();
    expect(screen.getByText("Plan may not fully fit before 2026-06-22.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /edit|done|accept|reject/i })).toBeNull();
    expect(container.querySelector('[draggable="true"]')).toBeNull();

    fireEvent.click(screen.getByTestId("workload-export-calendar"));
    await waitFor(() => expect(mocks.downloadWorkloadPlanCalendar).toHaveBeenCalledWith("plan-1"));
    expect(createObjectURL).toHaveBeenCalled();
    expect(clickAnchor).toHaveBeenCalled();
    expect(screen.getByTestId("workload-status").textContent).toBe("Calendar downloaded");

    fireEvent.click(screen.getByTestId("workload-generate"));
    await waitFor(() => expect(mocks.generateStudentWorkloadPlan).toHaveBeenCalledWith("module-1"));
    expect(screen.getByTestId("workload-status").textContent).toBe("Plan updated");
    clickAnchor.mockRestore();
  });
});
