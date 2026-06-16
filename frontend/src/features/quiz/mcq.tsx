"use client";

/**
 * Reusable, API-AGNOSTIC multiple-choice components (Stage 5d).
 *
 * These import NOTHING from the API client — they take plain props + callbacks, so Stage 7's glossary
 * Learn/Test reuses them unchanged (accessibility, and later KaTeX, fixed once here). Math/formulas
 * render as ESCAPED PLAIN TEXT (D-MATH): React escapes text by default and we never use
 * dangerouslySetInnerHTML, so a raw `$\lim_{x\to0}$` shows literally until Stage 7 adds KaTeX here.
 * Answers are FINAL once submitted (D-ABANDON): selecting an option IS the submit.
 */

import type React from "react";

export type McqOption = { id: string; text: string };

/** Post-answer result for one question. `null` = not yet answered. */
export type McqAnswer = {
  selectedOptionId: string;
  correctOptionId: string;
  isCorrect: boolean;
  explanation?: string | null;
  mistakeSaved: boolean;
} | null;

type OptionState = "idle" | "selected-correct" | "selected-incorrect" | "missed-correct";

function optionState(optionId: string, answer: McqAnswer): OptionState {
  if (answer === null) return "idle";
  if (optionId === answer.selectedOptionId) {
    return answer.isCorrect ? "selected-correct" : "selected-incorrect";
  }
  if (optionId === answer.correctOptionId) return "missed-correct";
  return "idle";
}

export function AnswerOptionButton({
  option,
  answer,
  disabled,
  onSelect,
}: {
  option: McqOption;
  answer: McqAnswer;
  disabled: boolean;
  onSelect: (optionId: string) => void;
}) {
  const state = optionState(option.id, answer);
  const style =
    state === "selected-correct" || state === "missed-correct"
      ? styles.optionCorrect
      : state === "selected-incorrect"
        ? styles.optionIncorrect
        : styles.option;
  return (
    <button
      type="button"
      data-testid={`quiz-option-${option.id}`}
      data-state={state}
      aria-pressed={answer?.selectedOptionId === option.id}
      disabled={disabled}
      onClick={() => onSelect(option.id)}
      style={style}
    >
      {option.text}
    </button>
  );
}

export function AnswerFeedbackPanel({ answer }: { answer: NonNullable<McqAnswer> }) {
  return (
    <div
      role="status"
      data-testid="quiz-feedback"
      data-correct={answer.isCorrect}
      style={answer.isCorrect ? styles.feedbackCorrect : styles.feedbackIncorrect}
    >
      <p style={styles.feedbackLabel}>{answer.isCorrect ? "Correct" : "Incorrect"}</p>
      {answer.explanation ? <p style={styles.feedbackText}>{answer.explanation}</p> : null}
      {answer.mistakeSaved ? (
        <p data-testid="quiz-mistake-saved" style={styles.mistakeNote}>
          Saved to your mistakes
        </p>
      ) : null}
    </div>
  );
}

export function MultipleChoiceQuestionCard({
  questionNumber,
  totalQuestions,
  questionText,
  options,
  answer,
  submitting,
  onSelect,
}: {
  questionNumber: number;
  totalQuestions: number;
  questionText: string;
  options: McqOption[];
  answer: McqAnswer;
  submitting: boolean;
  onSelect: (optionId: string) => void;
}) {
  const answered = answer !== null;
  return (
    <div data-testid="quiz-question-card" data-answered={answered} style={styles.card}>
      <p style={styles.progress}>
        Question {questionNumber} of {totalQuestions}
      </p>
      <p style={styles.questionText}>{questionText}</p>
      <div role="group" aria-label="Answer options" style={styles.options}>
        {options.map((option) => (
          <AnswerOptionButton
            key={option.id}
            option={option}
            answer={answer}
            disabled={answered || submitting}
            onSelect={onSelect}
          />
        ))}
      </div>
      {answered ? <AnswerFeedbackPanel answer={answer} /> : null}
    </div>
  );
}

export function QuizResultSummary({
  scorePercentage,
  correctCount,
  incorrectCount,
  totalQuestions,
  onStartOver,
  startingOver,
}: {
  scorePercentage: number | null;
  correctCount: number | null;
  incorrectCount: number | null;
  totalQuestions: number | null;
  onStartOver: () => void;
  startingOver: boolean;
}) {
  const mistakes = incorrectCount ?? 0;
  return (
    <div data-testid="quiz-result" style={styles.result}>
      <p style={styles.score} data-testid="quiz-score">
        {scorePercentage === null ? "—" : `${scorePercentage}%`}
      </p>
      <p style={styles.resultDetail}>
        {correctCount ?? 0} of {totalQuestions ?? 0} correct
      </p>
      <p style={styles.resultDetail} data-testid="quiz-mistakes-count">
        {mistakes === 1 ? "1 mistake recorded" : `${mistakes} mistakes recorded`}
      </p>
      <button
        type="button"
        data-testid="quiz-start-over"
        disabled={startingOver}
        onClick={onStartOver}
        style={styles.primaryButton}
      >
        {startingOver ? "Starting…" : "Start Over"}
      </button>
    </div>
  );
}

const styles = {
  card: { border: "1px solid #d7dde8", borderRadius: 8, display: "grid", gap: 12, padding: 16 },
  progress: { color: "#4b5563", fontSize: 12, fontWeight: 700, margin: 0, textTransform: "uppercase" },
  questionText: { color: "#111827", fontSize: 16, lineHeight: 1.4, margin: 0 },
  options: { display: "grid", gap: 8 },
  option: {
    background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6, color: "#111827",
    cursor: "pointer", fontSize: 14, padding: "10px 12px", textAlign: "left",
  },
  optionCorrect: {
    background: "#ecfdf5", border: "1px solid #059669", borderRadius: 6, color: "#065f46",
    fontSize: 14, padding: "10px 12px", textAlign: "left",
  },
  optionIncorrect: {
    background: "#fef2f2", border: "1px solid #b91c1c", borderRadius: 6, color: "#7f1d1d",
    fontSize: 14, padding: "10px 12px", textAlign: "left",
  },
  feedbackCorrect: {
    background: "#ecfdf5", border: "1px solid #a7f3d0", borderRadius: 6, display: "grid",
    gap: 4, padding: "10px 12px",
  },
  feedbackIncorrect: {
    background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, display: "grid",
    gap: 4, padding: "10px 12px",
  },
  feedbackLabel: { fontSize: 14, fontWeight: 700, margin: 0 },
  feedbackText: { color: "#374151", fontSize: 14, lineHeight: 1.5, margin: 0 },
  mistakeNote: { color: "#7f1d1d", fontSize: 13, fontStyle: "italic", margin: 0 },
  result: { border: "1px solid #d7dde8", borderRadius: 8, display: "grid", gap: 8, padding: 16 },
  score: { color: "#111827", fontSize: 32, fontWeight: 800, margin: 0 },
  resultDetail: { color: "#374151", fontSize: 14, margin: 0 },
  primaryButton: {
    background: "#174a63", border: "1px solid #174a63", borderRadius: 6, color: "#ffffff",
    cursor: "pointer", fontSize: 13, fontWeight: 700, justifySelf: "start", minHeight: 34,
    padding: "0 14px",
  },
} satisfies Record<string, React.CSSProperties>;
