import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { ConversationView } from "./ConversationView";
import type { MessageRead } from "../../lib/api";

// Stage 8.5 — runtime check of the <SaveToGlossary> affordance gating in the shared assistant render
// surface (the same logic the browser gate's two visible negative assertions cover). The api wrapper is
// mocked so this needs no backend/Supabase: we assert PRESENCE/ABSENCE of the affordance, never a save.

vi.mock("../../lib/api/wrapper", () => ({
  api: { glossary: { saveHighlight: vi.fn() } },
  ForbiddenError: class ForbiddenError extends Error {},
}));

const baseProps = {
  scope: "assistant",
  loading: false,
  hasPending: false,
  gone: false,
  capped: false,
  sending: false,
  error: null,
  draft: "",
  hasMore: false,
  loadingOlder: false,
  onSend: vi.fn(),
  onRetry: vi.fn(),
  onLoadOlder: vi.fn(),
  onDraftChange: vi.fn(),
} as const;

function msg(over: Partial<MessageRead>): MessageRead {
  return {
    id: "m1",
    role: "assistant",
    status: "completed",
    content: "A concise study answer.",
    createdAt: "2026-06-19T00:00:00Z",
    ...over,
  };
}

describe("ConversationView — Stage 8.5 save-to-glossary affordance gating", () => {
  it("mounts the affordance on a completed assistant reply in a section-bound conversation", () => {
    render(<ConversationView {...baseProps} messages={[msg({})]} conversationId="c1" saveSectionId="s1" />);
    expect(screen.getByTestId("save-to-glossary")).toBeTruthy();
  });

  it("does NOT mount the affordance on the student's OWN (user) message", () => {
    render(
      <ConversationView
        {...baseProps}
        messages={[
          msg({ id: "u1", role: "user", content: "what is mitochondria?" }),
          msg({ id: "a1" }),
        ]}
        conversationId="c1"
        saveSectionId="s1"
      />,
    );
    // exactly one affordance (for the assistant reply), and it is NOT inside the user row
    expect(screen.getAllByTestId("save-to-glossary")).toHaveLength(1);
    const userRow = screen.getByTestId("assistant-message-user");
    expect(within(userRow).queryByTestId("save-to-glossary")).toBeNull();
  });

  it("does NOT mount the affordance in an UNBOUND conversation (no saveSectionId)", () => {
    render(<ConversationView {...baseProps} messages={[msg({})]} conversationId="c1" saveSectionId={null} />);
    expect(screen.queryByTestId("save-to-glossary")).toBeNull();
  });

  it("does NOT mount the affordance until the conversationId is known", () => {
    render(<ConversationView {...baseProps} messages={[msg({})]} saveSectionId="s1" />);
    expect(screen.queryByTestId("save-to-glossary")).toBeNull();
  });

  it("does NOT mount the affordance on a pending or failed assistant reply", () => {
    const { rerender } = render(
      <ConversationView {...baseProps} messages={[msg({ status: "pending", content: null })]} conversationId="c1" saveSectionId="s1" />,
    );
    expect(screen.queryByTestId("save-to-glossary")).toBeNull();
    rerender(
      <ConversationView {...baseProps} messages={[msg({ status: "failed", content: null, failureMessage: "x" })]} conversationId="c1" saveSectionId="s1" />,
    );
    expect(screen.queryByTestId("save-to-glossary")).toBeNull();
  });
});
