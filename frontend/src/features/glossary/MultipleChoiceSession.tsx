"use client";

import { useState } from "react";

import type { PracticeSessionState } from "../../lib/api";
import { type McqAnswer, MultipleChoiceQuestionCard } from "../quiz/mcq";

// Stage 7c: Multiple-Choice (definition → term), REUSING the Stage 5 MCQ components unchanged (the
// definition is the question; the terms are the options; correctness rides on option identity). A
// "Don't know?" control reveals the answer and records the item as not-known. No AI runs here.

export function MultipleChoiceSession({
  session,
  onAnswer,
  onComplete,
}: {
  session: PracticeSessionState;
  onAnswer: (
    entryId: string,
    selectedEntryId: string | null,
  ) => Promise<{ isCorrect: boolean | null; correctEntryId: string | null }>;
  onComplete: () => void;
}) {
  const items = session.items;
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState<McqAnswer>(null);
  const [submitting, setSubmitting] = useState(false);
  const item = items[index];

  async function select(selectedEntryId: string | null) {
    if (answer || submitting || !item) return;
    setSubmitting(true);
    try {
      const fb = await onAnswer(item.entryId, selectedEntryId);
      setAnswer({
        selectedOptionId: selectedEntryId ?? "",
        correctOptionId: fb.correctEntryId ?? item.entryId,
        isCorrect: Boolean(fb.isCorrect),
        explanation: null,
        mistakeSaved: false,
      });
    } finally {
      setSubmitting(false);
    }
  }

  function next() {
    if (index + 1 >= items.length) {
      onComplete();
      return;
    }
    setIndex(index + 1);
    setAnswer(null);
  }

  if (!item) {
    return <p>No questions available.</p>;
  }
  const options = (item.options ?? []).map((o) => ({ id: o.entryId, text: o.term }));
  const last = index + 1 >= items.length;

  return (
    <div data-testid="glossary-mcq-session" style={styles.wrap}>
      <MultipleChoiceQuestionCard
        questionNumber={index + 1}
        totalQuestions={items.length}
        questionText={item.definition ?? "(definition unavailable)"}
        options={options}
        answer={answer}
        submitting={submitting}
        onSelect={(optionId) => void select(optionId)}
      />
      {answer ? (
        <button type="button" data-testid="glossary-mcq-next" onClick={next} style={styles.primary}>
          {last ? "Finish" : "Next"}
        </button>
      ) : (
        <button
          type="button"
          data-testid="glossary-mcq-dontknow"
          disabled={submitting}
          onClick={() => void select(null)}
          style={styles.secondary}
        >
          Don’t know?
        </button>
      )}
    </div>
  );
}

const styles = {
  wrap: { display: "grid", gap: 12 },
  primary: {
    background: "#174a63",
    border: "1px solid #174a63",
    borderRadius: 6,
    color: "#ffffff",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 700,
    justifySelf: "start",
    minHeight: 34,
    padding: "0 14px",
  },
  secondary: {
    background: "#ffffff",
    border: "1px solid #d7dde8",
    borderRadius: 6,
    color: "#374151",
    cursor: "pointer",
    fontSize: 13,
    justifySelf: "start",
    minHeight: 34,
    padding: "0 14px",
  },
} satisfies Record<string, React.CSSProperties>;
