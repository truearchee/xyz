import { describe, expect, test } from "bun:test";

import {
  decideSendAttempt,
  hasPendingAssistantTurn,
  type SendAttempt,
} from "../../frontend/src/features/assistant/sendIdempotency";

describe("assistant send idempotency", () => {
  test("reuses the same key for a retry of the same conversation attempt", () => {
    const existing: SendAttempt = { content: "Explain cells", key: "key-1" };
    const decision = decideSendAttempt({
      content: "  Explain cells  ",
      sending: false,
      hasPending: false,
      existingAttempt: existing,
      createKey: () => "key-2",
    });

    expect(decision).toEqual({ action: "send", attempt: existing });
  });

  test("rejects duplicate sends while the store is already sending or has a pending turn", () => {
    expect(
      decideSendAttempt({
        content: "Explain cells",
        sending: true,
        hasPending: false,
        existingAttempt: null,
        createKey: () => "key-1",
      }),
    ).toEqual({ action: "reject", reason: "busy" });

    expect(
      decideSendAttempt({
        content: "Explain cells",
        sending: false,
        hasPending: true,
        existingAttempt: null,
        createKey: () => "key-1",
      }),
    ).toEqual({ action: "reject", reason: "busy" });
  });

  test("uses a new key after the draft changes to a new attempt", () => {
    const decision = decideSendAttempt({
      content: "Explain genetics",
      sending: false,
      hasPending: false,
      existingAttempt: { content: "Explain cells", key: "key-1" },
      createKey: () => "key-2",
    });

    expect(decision).toEqual({ action: "send", attempt: { content: "Explain genetics", key: "key-2" } });
  });

  test("detects pending assistant turns from message status", () => {
    expect(hasPendingAssistantTurn([{ status: "completed" }, { status: "pending" }])).toBe(true);
    expect(hasPendingAssistantTurn([{ status: "completed" }, { status: "failed" }])).toBe(false);
  });
});
