"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { PracticeSessionState } from "../../lib/api";
import { MarkdownView } from "./MarkdownView";

// Stage 7b: Flashcards. Click the card to flip (term → definition). Rate with BOTH keyboard shortcuts
// (Left = "study again" / re-queue, Right = "I know this" / advance) AND an on-screen rating row
// (mobile/touch users can't press arrow keys — the row is required). Progress tracker = answered / total.

export function FlashcardsSession({
  session,
  onAnswer,
  onComplete,
}: {
  session: PracticeSessionState;
  onAnswer: (entryId: string, outcome: "known" | "not_known") => Promise<void>;
  onComplete: () => void;
}) {
  const byId = useMemo(
    () => new Map(session.items.map((i) => [i.entryId, i])),
    [session.items],
  );
  const total = session.items.length;
  const [queue, setQueue] = useState<string[]>(session.items.map((i) => i.entryId));
  const [answered, setAnswered] = useState<Set<string>>(new Set());
  const [flipped, setFlipped] = useState(false);

  const currentId = queue[0];
  const current = currentId ? byId.get(currentId) : undefined;

  const rate = useCallback(
    async (outcome: "known" | "not_known") => {
      if (!currentId) return;
      if (!answered.has(currentId)) {
        // The first rating is the one recorded; "study again" re-queues for STUDY only.
        await onAnswer(currentId, outcome);
        setAnswered((prev) => new Set(prev).add(currentId));
      }
      setFlipped(false);
      setQueue((prev) => {
        const [head, ...rest] = prev;
        const nextQueue = outcome === "not_known" ? [...rest, head] : rest;
        if (nextQueue.length === 0) {
          onComplete();
        }
        return nextQueue;
      });
    },
    [answered, currentId, onAnswer, onComplete],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!current) return;
      if (e.key === "ArrowRight") void rate("known");
      else if (e.key === "ArrowLeft") void rate("not_known");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, rate]);

  if (!current) {
    return <p data-testid="glossary-flashcards-done">All cards reviewed.</p>;
  }

  return (
    <div data-testid="glossary-flashcards-session" style={styles.wrap}>
      <p data-testid="glossary-flashcards-progress" style={styles.progress}>
        {answered.size} / {total}
      </p>
      <button
        type="button"
        data-testid="glossary-flashcard"
        data-flipped={flipped}
        onClick={() => setFlipped((f) => !f)}
        dir={current.language === "ar" ? "rtl" : "ltr"}
        style={styles.card}
      >
        {flipped ? (
          current.definition ? (
            <MarkdownView content={current.definition} language={current.language} />
          ) : (
            <span style={styles.muted}>No definition yet.</span>
          )
        ) : (
          <span style={styles.term}>{current.term}</span>
        )}
      </button>
      <p style={styles.hint}>{flipped ? "Rate how well you knew it" : "Click the card to flip"}</p>
      <div role="group" aria-label="Rate this card" style={styles.ratingRow}>
        <button
          type="button"
          data-testid="flashcard-study-again"
          onClick={() => void rate("not_known")}
          style={styles.again}
        >
          Study again (←)
        </button>
        <button
          type="button"
          data-testid="flashcard-know"
          onClick={() => void rate("known")}
          style={styles.know}
        >
          I know this (→)
        </button>
      </div>
    </div>
  );
}

const styles = {
  wrap: { display: "grid", gap: 12, justifyItems: "stretch" },
  progress: { color: "var(--color-text-muted)", fontSize: 13, fontWeight: 700, margin: 0 },
  card: {
    alignItems: "center",
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: 10,
    cursor: "pointer",
    display: "flex",
    justifyContent: "center",
    minHeight: 160,
    padding: 24,
    textAlign: "center",
  },
  term: { color: "var(--color-text)", fontSize: 22, fontWeight: 700 },
  muted: { color: "var(--color-text-muted)", fontSize: 14, fontStyle: "italic" },
  hint: { color: "var(--color-text-muted)", fontSize: 13, margin: 0, textAlign: "center" },
  ratingRow: { display: "flex", gap: 10, justifyContent: "center" },
  again: {
    background: "var(--color-warning-surface)",
    border: "1px solid var(--color-warning)",
    borderRadius: 6,
    color: "var(--color-warning-text)",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 700,
    minHeight: 40,
    padding: "0 18px",
  },
  know: {
    background: "var(--color-success-surface)",
    border: "1px solid var(--color-success)",
    borderRadius: 6,
    color: "var(--color-success-text)",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 700,
    minHeight: 40,
    padding: "0 18px",
  },
} satisfies Record<string, React.CSSProperties>;
