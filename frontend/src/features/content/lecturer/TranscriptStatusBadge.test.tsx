import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// §6.2 — status badge step mapping (the pipeline-status truth, 4.5/4.6). Asserted through the rendered
// component (the real mapping path): each step state → its badge text; "embed ok, summary failed" shows a
// FAILED summary while earlier steps stay completed; a terminal failure surfaces retryable correctly; no
// combination yields a blank/contradictory badge.

const { getProcessingStatus, retry } = vi.hoisted(() => ({
  getProcessingStatus: vi.fn(),
  retry: vi.fn(),
}));
vi.mock("../../../lib/api/wrapper", () => ({
  api: { transcripts: { getProcessingStatus, retry } },
}));
vi.mock("../../../lib/api", () => ({
  ApiError: class ApiError extends Error {
    status = 0;
    body: unknown;
  },
}));

import { TranscriptStatusBadge } from "./TranscriptStatusBadge";

const KEY = "k1";
const transcript = { id: "t1", status: "processing" } as never;

type Steps = Partial<Record<"parse" | "chunk" | "embed" | "summaryBrief" | "summaryDetailed", string>>;
function makeStatus(overallState: string, steps: Steps, extra: Record<string, unknown> = {}) {
  const s = (v?: string) => ({ status: v ?? "pending" });
  return {
    overallState,
    activeTranscriptId: "t1",
    failedStep: null,
    retryable: false,
    safeFailureMessage: null,
    currentPhase: null,
    steps: {
      parse: s(steps.parse),
      chunk: s(steps.chunk),
      embed: s(steps.embed),
      summaryBrief: s(steps.summaryBrief),
      summaryDetailed: s(steps.summaryDetailed),
    },
    ...extra,
  };
}

function renderBadge() {
  return render(
    <TranscriptStatusBadge
      moduleId="m1"
      onTranscriptMissing={() => {}}
      sectionId="s1"
      sectionKey={KEY}
      transcript={transcript}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  retry.mockResolvedValue(makeStatus("queued", {}));
});

describe("status badge — overall mapping", () => {
  it("summarized → 'Summaries ready' (non-blank)", async () => {
    getProcessingStatus.mockResolvedValue(
      makeStatus("summarized", {
        parse: "completed",
        chunk: "completed",
        embed: "completed",
        summaryBrief: "completed",
        summaryDetailed: "completed",
      }),
    );
    renderBadge();
    const badge = await screen.findByTestId(`section-transcript-status-${KEY}`);
    expect(badge.textContent?.trim()).toBe("Summaries ready");
  });
});

describe("status badge — 'embed ok, summary failed' (Stage 4.5 prereq #3)", () => {
  it("renders a FAILED summary step while earlier steps stay completed, and a retryable failure shows Retry", async () => {
    getProcessingStatus.mockResolvedValue(
      makeStatus(
        "failed",
        {
          parse: "completed",
          chunk: "completed",
          embed: "completed",
          summaryBrief: "failed",
          summaryDetailed: "pending",
        },
        { failedStep: "summaryBrief", retryable: true, safeFailureMessage: "Summary generation failed." },
      ),
    );
    renderBadge();

    // overall status surfaces the failure message (not blank)
    const badge = await screen.findByTestId(`section-transcript-status-${KEY}`);
    expect(badge.textContent).toContain("Summary generation failed.");

    // the steps list: earlier steps completed, the summary step FAILED (explicit text, not just colour)
    const steps = screen.getByTestId(`section-transcript-steps-${KEY}`);
    expect(steps.textContent).toContain("Embed");
    expect(steps.textContent).toContain("completed");
    expect(steps.textContent).toContain("failed");

    // retryable terminal failure → retry control present
    expect(screen.getByTestId(`section-transcript-retry-${KEY}`)).toBeTruthy();
  });

  it("a NON-retryable terminal failure shows NO retry control", async () => {
    getProcessingStatus.mockResolvedValue(
      makeStatus(
        "failed",
        { parse: "completed", chunk: "failed", embed: "pending", summaryBrief: "pending", summaryDetailed: "pending" },
        { failedStep: "chunk", retryable: false, safeFailureMessage: "Chunking failed." },
      ),
    );
    renderBadge();
    await screen.findByTestId(`section-transcript-status-${KEY}`);
    expect(screen.queryByTestId(`section-transcript-retry-${KEY}`)).toBeNull();
  });
});

describe("status badge — no blank/contradictory badge across states", () => {
  it("every in-flight overall state yields non-empty status text", async () => {
    for (const state of ["queued", "parsing", "chunking", "embedding", "summarizing"]) {
      getProcessingStatus.mockResolvedValue(makeStatus(state, { parse: "running" }));
      const { unmount } = renderBadge();
      const badge = await screen.findByTestId(`section-transcript-status-${KEY}`);
      expect((badge.textContent ?? "").trim().length).toBeGreaterThan(0);
      unmount();
    }
  });
});
