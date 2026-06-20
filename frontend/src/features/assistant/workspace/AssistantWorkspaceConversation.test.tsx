import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { AssistantWorkspaceConversation } from "./AssistantWorkspaceConversation";

// Stage 8.6b — the exam-prep quiz pointer maps the EXISTING quiz endpoint's (available, reasonCode) to
// exactly ONE of three conversation-surface states; the assistant never invents availability. This is the
// fast, stack-free complement to the browser gate's three LIVE cases (ready / processing / none). The
// store, router, and api wrapper are mocked so only the mapping + render is under test.

const getConversation = vi.fn();
const listExamPrepScopes = vi.fn();
const loadInitial = vi.fn();
const markDeleted = vi.fn();
const send = vi.fn();
const retry = vi.fn();
const loadOlder = vi.fn();
const setDraft = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("../AssistantStoreProvider", () => ({
  useAssistantStore: () => ({ loadInitial, markDeleted }),
  useAssistantConversation: () => ({
    messages: [],
    loading: false,
    hasPending: false,
    gone: false,
    capped: false,
    sending: false,
    error: null,
    draft: "",
    hasMore: false,
    loadingOlder: false,
    send,
    retry,
    loadOlder,
    setDraft,
  }),
}));

vi.mock("../../../lib/api/wrapper", () => ({
  api: {
    assistant: { getConversation: (...args: unknown[]) => getConversation(...args) },
    quiz: { listExamPrepScopes: (...args: unknown[]) => listExamPrepScopes(...args) },
    glossary: { saveHighlight: vi.fn() },
  },
  ForbiddenError: class ForbiddenError extends Error {},
}));

const SCOPE_ID = "11111111-1111-4111-8111-111111111111";
const MODULE_ID = "22222222-2222-4222-8222-222222222222";

function examPrepDetail() {
  return {
    id: "c1",
    conversationKind: "exam_prep",
    assessmentScopeId: SCOPE_ID,
    assessmentScopeName: "Midterm",
    moduleId: MODULE_ID,
    moduleTitle: "Biology",
    coveredWeeks: [1, 2],
    displayTitle: "Exam prep — Midterm",
    groundingChip: "Exam prep",
    attachedSectionId: null,
  };
}

function scope(over: { available: boolean; reasonCode: string | null }) {
  return [{ id: SCOPE_ID, name: "Midterm", coveredWeeks: [1, 2], ...over }];
}

beforeEach(() => {
  getConversation.mockReset();
  listExamPrepScopes.mockReset();
  loadInitial.mockReset();
  markDeleted.mockReset();
  send.mockReset();
  retry.mockReset();
  loadOlder.mockReset();
  setDraft.mockReset();
  getConversation.mockResolvedValue(examPrepDetail());
});

describe("AssistantWorkspaceConversation — exam-prep quiz pointer (8.6b, all three states)", () => {
  it("available → 'Practice with the exam-prep quiz' CTA linking to the module, no muted state", async () => {
    listExamPrepScopes.mockResolvedValue(scope({ available: true, reasonCode: null }));
    render(<AssistantWorkspaceConversation conversationId="c1" />);
    const cta = await screen.findByTestId("assistant-examprep-quiz-cta");
    expect(cta.getAttribute("href")).toBe(`/student/modules/${MODULE_ID}`);
    expect(cta.textContent).toContain("Practice with the exam-prep quiz");
    expect(screen.queryByTestId("assistant-examprep-quiz-state")).toBeNull();
  });

  it("processing → 'Practice quiz is being prepared', NEVER a CTA", async () => {
    listExamPrepScopes.mockResolvedValue(scope({ available: false, reasonCode: "processing" }));
    render(<AssistantWorkspaceConversation conversationId="c1" />);
    const state = await screen.findByTestId("assistant-examprep-quiz-state");
    expect(state.textContent).toBe("Practice quiz is being prepared");
    expect(screen.queryByTestId("assistant-examprep-quiz-cta")).toBeNull();
  });

  it("no eligible sections → 'Practice quiz not available yet', NEVER a CTA", async () => {
    listExamPrepScopes.mockResolvedValue(scope({ available: false, reasonCode: "no_eligible_sections" }));
    render(<AssistantWorkspaceConversation conversationId="c1" />);
    const state = await screen.findByTestId("assistant-examprep-quiz-state");
    expect(state.textContent).toBe("Practice quiz not available yet");
    expect(screen.queryByTestId("assistant-examprep-quiz-cta")).toBeNull();
  });

  it("any other unavailable reason still resolves to 'not available yet' (never fabricates a CTA)", async () => {
    listExamPrepScopes.mockResolvedValue(scope({ available: false, reasonCode: null }));
    render(<AssistantWorkspaceConversation conversationId="c1" />);
    const state = await screen.findByTestId("assistant-examprep-quiz-state");
    expect(state.textContent).toBe("Practice quiz not available yet");
    expect(screen.queryByTestId("assistant-examprep-quiz-cta")).toBeNull();
  });
});

describe("AssistantWorkspaceConversation — time-management mode (8.6c)", () => {
  it("renders structured-data context and time-management starters", async () => {
    getConversation.mockResolvedValue({
      id: "tm1",
      conversationKind: "time_management",
      displayTitle: "Time management",
      groundingChip: "Time management",
      moduleId: null,
      moduleTitle: null,
      attachedSectionId: null,
      sectionTitle: null,
      sectionType: null,
      lastActivityAt: new Date().toISOString(),
      messageCount: 0,
    });
    render(<AssistantWorkspaceConversation conversationId="tm1" />);
    expect((await screen.findByTestId("assistant-mode-label")).textContent).toBe("Time management");
    expect(screen.getByTestId("assistant-context-pill").textContent).toContain("Your deadlines and progress");
    expect(screen.getByTestId("workspace-time-management-starters")).toBeTruthy();
    expect(screen.queryByTestId("assistant-open-lecture")).toBeNull();
  });
});
