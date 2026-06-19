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
  const className =
    state === "selected-correct" || state === "missed-correct"
      ? classes.optionCorrect
      : state === "selected-incorrect"
        ? classes.optionIncorrect
        : classes.option;
  return (
    <button
      type="button"
      data-testid={`quiz-option-${option.id}`}
      data-state={state}
      aria-pressed={answer?.selectedOptionId === option.id}
      disabled={disabled}
      onClick={() => onSelect(option.id)}
      className={className}
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
      className={answer.isCorrect ? classes.feedbackCorrect : classes.feedbackIncorrect}
    >
      <p className={classes.feedbackLabel}>{answer.isCorrect ? "Correct" : "Incorrect"}</p>
      {answer.explanation ? <p className={classes.feedbackText}>{answer.explanation}</p> : null}
      {answer.mistakeSaved ? (
        <p data-testid="quiz-mistake-saved" className={classes.mistakeNote}>
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
    <div data-testid="quiz-question-card" data-answered={answered} className={classes.card}>
      <p className={classes.progress}>
        Question {questionNumber} of {totalQuestions}
      </p>
      <p className={classes.questionText}>{questionText}</p>
      <div role="group" aria-label="Answer options" className={classes.options}>
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
    <div data-testid="quiz-result" className={classes.result}>
      <p className={classes.score} data-testid="quiz-score">
        {scorePercentage === null ? "-" : `${scorePercentage}%`}
      </p>
      <p className={classes.resultDetail}>
        {correctCount ?? 0} of {totalQuestions ?? 0} correct
      </p>
      <p className={classes.resultDetail} data-testid="quiz-mistakes-count">
        {mistakes === 1 ? "1 mistake recorded" : `${mistakes} mistakes recorded`}
      </p>
      <button
        type="button"
        data-testid="quiz-start-over"
        disabled={startingOver}
        onClick={onStartOver}
        className={classes.primaryButton}
      >
        {startingOver ? "Starting..." : "Start Over"}
      </button>
    </div>
  );
}

const classes = {
  card: "grid gap-3 rounded-lg border border-border bg-surface p-4",
  progress: "m-0 text-xs font-semibold uppercase text-text-muted",
  questionText: "m-0 text-base leading-6 text-text",
  options: "grid gap-2",
  option:
    "rounded-md border border-border bg-surface px-3 py-2.5 text-left text-sm text-text hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-80 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2",
  optionCorrect: "rounded-md border border-success bg-success-surface px-3 py-2.5 text-left text-sm text-success-text",
  optionIncorrect: "rounded-md border border-danger bg-danger-surface px-3 py-2.5 text-left text-sm text-danger-text",
  feedbackCorrect: "grid gap-1 rounded-md border border-success bg-success-surface px-3 py-2.5",
  feedbackIncorrect: "grid gap-1 rounded-md border border-danger bg-danger-surface px-3 py-2.5",
  feedbackLabel: "m-0 text-sm font-semibold text-text",
  feedbackText: "m-0 text-sm leading-6 text-text-muted",
  mistakeNote: "m-0 text-sm italic text-danger-text",
  result: "grid gap-2 rounded-lg border border-border bg-surface p-4",
  score: "m-0 text-3xl font-semibold text-text",
  resultDetail: "m-0 text-sm text-text-muted",
  primaryButton:
    "min-h-9 justify-self-start rounded-full border border-primary bg-primary px-4 text-sm font-semibold text-on-primary hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2",
} as const;
