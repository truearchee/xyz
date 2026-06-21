import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { WidgetDrawer } from "./WidgetDrawer";

const listConversations = vi.fn();

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: { children: ReactNode; href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../a11y/useFocusTrap", () => ({
  useFocusTrap: vi.fn(),
}));

vi.mock("../AssistantStoreProvider", () => ({
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
    send: vi.fn(),
    retry: vi.fn(),
    loadOlder: vi.fn(),
    setDraft: vi.fn(),
  }),
}));

vi.mock("../../../lib/api/wrapper", () => ({
  api: {
    assistant: {
      listConversations: (...args: unknown[]) => listConversations(...args),
    },
    glossary: { saveHighlight: vi.fn() },
  },
  ForbiddenError: class ForbiddenError extends Error {},
}));

describe("WidgetDrawer recents", () => {
  it("renders section, module-only, and moduleless mode contexts without dangling separators", async () => {
    listConversations.mockResolvedValue({
      items: [
        {
          id: "lecture-1",
          conversationKind: "lecture",
          displayTitle: "Lecture chat",
          moduleTitle: "Calculus",
          sectionTitle: "Derivatives",
          lastActivityAt: "2026-06-20T00:00:00Z",
          messageCount: 1,
          groundingChip: "Lecture grounded",
        },
        {
          id: "homework-1",
          conversationKind: "homework_help",
          displayTitle: "Homework help",
          moduleTitle: "Calculus",
          sectionTitle: null,
          lastActivityAt: "2026-06-20T00:00:00Z",
          messageCount: 1,
          groundingChip: "Homework help",
        },
        {
          id: "time-1",
          conversationKind: "time_management",
          displayTitle: "Time management",
          moduleTitle: null,
          sectionTitle: null,
          lastActivityAt: "2026-06-20T00:00:00Z",
          messageCount: 1,
          groundingChip: "Time management",
        },
      ],
      pagination: { limit: 5, offset: 0, total: 3 },
    });

    render(
      <WidgetDrawer
        mode="recents"
        conversationId={null}
        lectureStatus={null}
        moduleId={null}
        sectionId={null}
        onClose={vi.fn()}
      />,
    );

    const list = await screen.findByTestId("assistant-widget-recents");
    const rows = within(list).getAllByTestId("assistant-widget-recent");
    expect(rows[0].textContent).toContain("Calculus → Derivatives");
    expect(rows[1].textContent).toContain("Calculus");
    expect(rows[1].textContent).not.toContain("→");
    expect(rows[2].textContent).toContain("Your deadlines and progress");
    expect(rows[2].textContent).not.toContain("→");
  });
});
