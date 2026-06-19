"use client";

import { useCallback, useEffect, useState } from "react";
import type React from "react";

import {
  type AnswerForStudent,
  type AnswerFeedback,
  type QuizAttemptForStudent,
} from "../../lib/api";
import { api } from "../../lib/api/wrapper";
import {
  MultipleChoiceQuestionCard,
  QuizResultSummary,
  type McqAnswer,
} from "./mcq";

const POLL_INITIAL_MS = 1500;
const POLL_MAX_MS = 12_000;
const POLL_BACKOFF = 1.5;
const POLL_WALLCLOCK_CAP_MS = 5 * 60_000;

function answerFromEmbedded(a: AnswerForStudent): McqAnswer {
  return {
    selectedOptionId: a.selectedAnswerOptionId,
    correctOptionId: a.correctAnswerOptionId,
    isCorrect: a.isCorrect,
    explanation: a.explanation ?? null,
    mistakeSaved: !a.isCorrect,
  };
}

function answerFromFeedback(fb: AnswerFeedback): McqAnswer {
  return {
    selectedOptionId: fb.selectedAnswerOptionId,
    correctOptionId: fb.correctAnswerOptionId,
    isCorrect: fb.isCorrect,
    explanation: fb.explanation ?? null,
    mistakeSaved: fb.mistakeSaved ?? false,
  };
}

function answersFromAttempt(attempt: QuizAttemptForStudent): Record<string, McqAnswer> {
  const map: Record<string, McqAnswer> = {};
  for (const q of attempt.questions ?? []) {
    map[q.id] = q.answer ? answerFromEmbedded(q.answer) : null;
  }
  return map;
}

export function QuizAttemptPanel({
  attempt: initialAttempt,
  label,
  onStartOver,
}: {
  attempt: QuizAttemptForStudent;
  label: string;
  onStartOver: () => Promise<QuizAttemptForStudent>;
}) {
  const [attempt, setAttempt] = useState(initialAttempt);
  const [answers, setAnswers] = useState<Record<string, McqAnswer>>(
    answersFromAttempt(initialAttempt),
  );
  const [busy, setBusy] = useState(false);
  const [submittingQ, setSubmittingQ] = useState<string | null>(null);
  const [capped, setCapped] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyAttempt = useCallback((next: QuizAttemptForStudent) => {
    setAttempt(next);
    setAnswers(answersFromAttempt(next));
  }, []);

  useEffect(() => {
    applyAttempt(initialAttempt);
    setError(null);
    setCapped(false);
  }, [initialAttempt, applyAttempt]);

  useEffect(() => {
    if (attempt.status !== "generating") return;
    let mounted = true;
    let timeoutId = 0;
    let delay = POLL_INITIAL_MS;
    let startedAt = 0;
    const attemptId = attempt.id;

    const tick = async (): Promise<void> => {
      try {
        const next = await api.quiz.getAttempt(attemptId);
        if (!mounted) return;
        applyAttempt(next);
        if (next.status !== "generating") return;
      } catch {
        if (!mounted) return;
      }
      if (!mounted) return;
      if (startedAt === 0) startedAt = Date.now();
      else if (Date.now() - startedAt > POLL_WALLCLOCK_CAP_MS) {
        setCapped(true);
        return;
      }
      delay = Math.min(Math.round(delay * POLL_BACKOFF), POLL_MAX_MS);
      timeoutId = window.setTimeout(() => void tick(), delay);
    };
    void tick();
    return () => {
      mounted = false;
      window.clearTimeout(timeoutId);
    };
  }, [attempt.id, attempt.status, applyAttempt]);

  const startOver = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await onStartOver();
      applyAttempt(next);
      setCapped(false);
    } catch {
      setError("Could not start the quiz - try again.");
    } finally {
      setBusy(false);
    }
  }, [onStartOver, applyAttempt]);

  const retryFailed = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await api.quiz.retryAttempt(attempt.id);
      applyAttempt(next);
      setCapped(false);
    } catch {
      setError("Could not retry this quiz - try again.");
    } finally {
      setBusy(false);
    }
  }, [attempt.id, applyAttempt]);

  const onAnswer = useCallback(
    async (questionId: string, optionId: string) => {
      if (answers[questionId]) return;
      setSubmittingQ(questionId);
      setError(null);
      try {
        const fb = await api.quiz.answer(attempt.id, {
          questionId,
          selectedAnswerOptionId: optionId,
        });
        setAnswers((prev) => ({ ...prev, [questionId]: answerFromFeedback(fb) }));
      } catch {
        setError("Could not record that answer - try again.");
      } finally {
        setSubmittingQ(null);
      }
    },
    [attempt.id, answers],
  );

  const onComplete = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await api.quiz.complete(attempt.id);
      const refreshed = await api.quiz.getAttempt(attempt.id);
      applyAttempt(refreshed);
    } catch {
      setError("Could not submit - try again.");
    } finally {
      setBusy(false);
    }
  }, [attempt.id, applyAttempt]);

  if (attempt.status === "generating") {
    return (
      <section aria-label={label} data-testid="quiz-attempt-panel" className={classes.block}>
        <h2 className={classes.blockHeading}>{label}</h2>
        <div role="status" data-testid="quiz-generating" className={classes.progressBox}>
          <p className={classes.bodyText}>
            {capped ? "Still preparing - refresh to check." : "Generating your quiz."}
          </p>
          <div aria-hidden="true" className={classes.progressTrack}>
            <span className={classes.progressFill} />
          </div>
        </div>
      </section>
    );
  }

  if (attempt.status === "failed") {
    return (
      <section aria-label={label} data-testid="quiz-attempt-panel" className={classes.block}>
        <h2 className={classes.blockHeading}>{label}</h2>
        <p role="alert" className={classes.muted}>We could not prepare this quiz.</p>
        {error ? <p role="alert" className={classes.muted}>{error}</p> : null}
        <button
          type="button"
          data-testid="quiz-retry-failed"
          disabled={busy}
          onClick={() => void retryFailed()}
          className={classes.primaryButton}
        >
          {busy ? "Retrying..." : "Try again"}
        </button>
      </section>
    );
  }

  if (attempt.status === "completed") {
    return (
      <section aria-label={label} data-testid="quiz-attempt-panel" className={classes.block}>
        <h2 className={classes.blockHeading}>{label}</h2>
        <QuizResultSummary
          scorePercentage={scoreOf(attempt)}
          correctCount={countAnswers(answers, true)}
          incorrectCount={countAnswers(answers, false)}
          totalQuestions={attempt.totalQuestions ?? (attempt.questions ?? []).length}
          onStartOver={() => void startOver()}
          startingOver={busy}
        />
      </section>
    );
  }

  const questions = attempt.questions ?? [];
  const total = attempt.totalQuestions ?? questions.length;
  const allAnswered = questions.length > 0 && questions.every((q) => answers[q.id]);
  const prefixCount = attempt.mistakeReviewQuestionCount ?? 0;
  return (
    <section aria-label={label} data-testid="quiz-attempt-panel" className={classes.block}>
      <h2 className={classes.blockHeading}>{label}</h2>
      {prefixCount > 0 ? (
        <div data-testid="quiz-retake-prefix-banner" role="status" className={classes.prefixBanner}>
          {prefixCount === 1
            ? "1 missed question is first in this retake."
            : `${prefixCount} missed questions are first in this retake.`}
        </div>
      ) : null}
      <div className={classes.questions}>
        {questions.map((q, i) => (
          <MultipleChoiceQuestionCard
            key={q.id}
            questionNumber={i + 1}
            totalQuestions={total}
            questionText={q.questionText}
            options={q.options.map((o) => ({ id: o.id, text: o.text }))}
            answer={answers[q.id] ?? null}
            submitting={submittingQ === q.id}
            onSelect={(optionId) => void onAnswer(q.id, optionId)}
          />
        ))}
      </div>
      {error ? <p role="alert" className={classes.muted}>{error}</p> : null}
      <button
        type="button"
        data-testid="quiz-complete"
        disabled={!allAnswered || busy}
        onClick={() => void onComplete()}
        className={classes.primaryButton}
      >
        {busy ? "Submitting..." : "See results"}
      </button>
    </section>
  );
}

function countAnswers(answers: Record<string, McqAnswer>, correct: boolean): number {
  return Object.values(answers).filter((a) => a !== null && a.isCorrect === correct).length;
}

function scoreOf(attempt: QuizAttemptForStudent): number | null {
  const qs = attempt.questions ?? [];
  const total = attempt.totalQuestions ?? qs.length;
  if (!total) return null;
  const correct = qs.filter((q) => q.answer?.isCorrect).length;
  return Math.round((correct / total) * 100 * 100) / 100;
}

const classes = {
  block: "grid gap-3 rounded-lg border border-border bg-surface p-4",
  blockHeading: "m-0 text-xs font-semibold uppercase text-text",
  bodyText: "m-0 text-sm leading-6 text-text",
  muted: "m-0 text-sm italic text-text-muted",
  prefixBanner: "rounded-md border border-warning bg-warning-surface px-3 py-2.5 text-sm leading-6 text-warning-text",
  progressBox: "grid gap-2.5",
  progressTrack: "h-2 w-full overflow-hidden rounded-full bg-surface-muted",
  progressFill: "block h-full w-[44%] rounded-full bg-primary",
  questions: "grid gap-3.5",
  primaryButton:
    "min-h-9 justify-self-start rounded-full border border-primary bg-primary px-4 text-sm font-semibold text-on-primary hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2",
} as const;
