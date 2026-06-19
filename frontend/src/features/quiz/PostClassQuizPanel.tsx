"use client";

/**
 * Post-class quiz panel (Stage 5d). Wires the API-agnostic MCQ components to `api.quiz`. States:
 * unavailable (passive) · available (Start) · generating (poll, 4.5d backoff, no 60s timeout) ·
 * in-progress (resumes on reload; immediate per-answer feedback; answers final) · results (score +
 * mistakes count + Start Over) · failed (sanitized + Start Over) · history line (best · attempts).
 *
 * The panel is the ONLY place that knows this is post-class; the MCQ components stay API-agnostic.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  type AnswerForStudent,
  type AnswerFeedback,
  type QuizAttemptForStudent,
  type QuizAttemptsSummary,
  type QuizAvailabilityResponse,
} from "../../lib/api";
import { ForbiddenError, api } from "../../lib/api/wrapper";
import {
  MultipleChoiceQuestionCard,
  QuizResultSummary,
  type McqAnswer,
} from "./mcq";

// Reuse the 4.5d backoff (no hard timeout). The "generating" state absorbs cohort-burst queue wait;
// a generous wall-clock ceiling, after which we ask the student to refresh.
const POLL_INITIAL_MS = 1500;
const POLL_MAX_MS = 12_000;
const POLL_BACKOFF = 1.5;
const POLL_WALLCLOCK_CAP_MS = 5 * 60_000;

const STORAGE_PREFIX = "xyz.quiz.attempt.";

function answerFromEmbedded(a: AnswerForStudent): McqAnswer {
  // In Stage 5 every wrong answer becomes a mistake, so mistakeSaved is derivable on resume.
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

export function PostClassQuizPanel({ sectionId }: { sectionId: string }) {
  const [availability, setAvailability] = useState<QuizAvailabilityResponse | null>(null);
  const [history, setHistory] = useState<QuizAttemptsSummary | null>(null);
  const [attempt, setAttempt] = useState<QuizAttemptForStudent | null>(null);
  const [answers, setAnswers] = useState<Record<string, McqAnswer>>({});
  const [busy, setBusy] = useState(false); // start / complete in flight
  const [submittingQ, setSubmittingQ] = useState<string | null>(null);
  const [capped, setCapped] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const storageKey = `${STORAGE_PREFIX}${sectionId}`;
  const rememberAttempt = useCallback(
    (id: string | null) => {
      try {
        if (id) window.sessionStorage.setItem(storageKey, id);
        else window.sessionStorage.removeItem(storageKey);
      } catch {
        /* storage unavailable — resume falls back to the Start button */
      }
    },
    [storageKey],
  );

  const applyAttempt = useCallback((next: QuizAttemptForStudent) => {
    setAttempt(next);
    setAnswers(answersFromAttempt(next));
  }, []);

  // Initial load: availability + history, and resume a remembered attempt (read-only, never creates).
  useEffect(() => {
    let mounted = true;
    setAvailability(null);
    setAttempt(null);
    setAnswers({});
    setCapped(false);
    setError(null);
    void (async () => {
      let storedId: string | null = null;
      try {
        storedId = window.sessionStorage.getItem(storageKey);
      } catch {
        storedId = null;
      }
      try {
        const [avail, hist] = await Promise.all([
          api.quiz.getAvailability(sectionId),
          api.quiz.getAttemptsSummary(sectionId),
        ]);
        if (!mounted) return;
        setAvailability(avail);
        setHistory(hist);
      } catch (caught) {
        if (!mounted) return;
        if (caught instanceof ForbiddenError || (caught instanceof ApiError && caught.status === 404)) {
          setAvailability({ availability: "unavailable", reasonCode: undefined });
        } else {
          setError("Couldn’t load the quiz — refresh to try again.");
        }
        return;
      }
      if (storedId) {
        try {
          const resumed = await api.quiz.getAttempt(storedId);
          if (!mounted) return;
          applyAttempt(resumed);
        } catch {
          // 404/gone/hidden → drop the stale pointer; fall back to availability.
          rememberAttempt(null);
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, [sectionId, storageKey, applyAttempt, rememberAttempt]);

  // Generating poll (4.5d backoff): runs only while the active attempt is `generating`.
  useEffect(() => {
    if (attempt === null || attempt.status !== "generating") return;
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
        if (next.status !== "generating") return; // terminal/in_progress — stop
      } catch {
        if (!mounted) return; // transient — keep polling
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
  }, [attempt, applyAttempt]);

  const onStart = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const started = await api.quiz.start(sectionId);
      rememberAttempt(started.id);
      applyAttempt(started);
      setCapped(false);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setError("This quiz isn’t ready yet.");
      } else if (caught instanceof ForbiddenError || (caught instanceof ApiError && caught.status === 404)) {
        setAvailability({ availability: "unavailable", reasonCode: undefined });
      } else {
        setError("Couldn’t start the quiz — try again.");
      }
    } finally {
      setBusy(false);
    }
  }, [sectionId, applyAttempt, rememberAttempt]);

  const onAnswer = useCallback(
    async (questionId: string, optionId: string) => {
      if (attempt === null || answers[questionId]) return; // answers are final
      setSubmittingQ(questionId);
      try {
        const fb = await api.quiz.answer(attempt.id, {
          questionId,
          selectedAnswerOptionId: optionId,
        });
        setAnswers((prev) => ({ ...prev, [questionId]: answerFromFeedback(fb) }));
      } catch {
        setError("Couldn’t record that answer — try again.");
      } finally {
        setSubmittingQ(null);
      }
    },
    [attempt, answers],
  );

  const onComplete = useCallback(async () => {
    if (attempt === null) return;
    setBusy(true);
    try {
      const result = await api.quiz.complete(attempt.id);
      setAttempt((prev) => (prev ? { ...prev, status: result.status } : prev));
      const [hist] = await Promise.all([api.quiz.getAttemptsSummary(sectionId)]);
      setHistory(hist);
      // Refetch the attempt so the result view has authoritative counts/score.
      const refreshed = await api.quiz.getAttempt(attempt.id);
      applyAttempt(refreshed);
      rememberAttempt(null); // attempt is terminal — Start Over makes a new one
    } catch {
      setError("Couldn’t submit — try again.");
    } finally {
      setBusy(false);
    }
  }, [attempt, sectionId, applyAttempt, rememberAttempt]);

  // ── render ─────────────────────────────────────────────────────────────────────────────────────
  const historyLine =
    history && history.attemptCount > 0 ? (
      <p data-testid="quiz-history" style={styles.history}>
        Best score{" "}
        {history.bestScorePercentage === null || history.bestScorePercentage === undefined
          ? "—"
          : `${history.bestScorePercentage}%`}{" "}
        · {history.attemptCount} attempt{history.attemptCount === 1 ? "" : "s"}
      </p>
    ) : null;

  function body() {
    if (error && attempt === null && availability === null) {
      return <p role="alert" style={styles.muted}>{error}</p>;
    }
    if (attempt !== null) {
      if (attempt.status === "generating") {
        return (
          <p role="status" data-testid="quiz-generating" style={styles.muted}>
            {capped ? "Still generating — refresh to check." : "Generating your quiz…"}
          </p>
        );
      }
      if (attempt.status === "failed") {
        return (
          <div data-testid="quiz-failed" style={styles.failed}>
            <p style={styles.muted}>We couldn’t generate this quiz.</p>
            <button type="button" data-testid="quiz-start-over" disabled={busy} onClick={() => void onStart()} style={styles.primaryButton}>
              {busy ? "Starting…" : "Start Over"}
            </button>
          </div>
        );
      }
      if (attempt.status === "completed") {
        return (
          <QuizResultSummary
            scorePercentage={scoreOf(attempt)}
            correctCount={countAnswers(answers, true)}
            incorrectCount={countAnswers(answers, false)}
            totalQuestions={attempt.totalQuestions ?? (attempt.questions ?? []).length}
            onStartOver={() => void onStart()}
            startingOver={busy}
          />
        );
      }
      // in_progress
      const questions = attempt.questions ?? [];
      const total = attempt.totalQuestions ?? questions.length;
      const allAnswered = questions.length > 0 && questions.every((q) => answers[q.id]);
      return (
        <div style={styles.questions}>
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
          {error ? <p role="alert" style={styles.muted}>{error}</p> : null}
          <button
            type="button"
            data-testid="quiz-complete"
            data-assistant-safe-area
            disabled={!allAnswered || busy}
            onClick={() => void onComplete()}
            style={styles.primaryButton}
          >
            {busy ? "Submitting…" : "See results"}
          </button>
        </div>
      );
    }
    // No active attempt → availability-driven.
    if (availability === null) {
      return <p style={styles.muted}>Loading quiz...</p>;
    }
    if (availability.availability !== "available") {
      return (
        <p data-testid="quiz-unavailable" role="status" style={styles.muted}>
          {availability.reasonCode === "summary_processing"
            ? "A quiz will be available once this lecture’s summary is ready."
            : "No quiz is available for this section yet."}
        </p>
      );
    }
    return (
      <div style={styles.startBlock}>
        <p style={styles.bodyText}>Check your understanding with a short quiz.</p>
        <button type="button" data-testid="quiz-start" disabled={busy} onClick={() => void onStart()} style={styles.primaryButton}>
          {busy ? "Starting..." : "Start quiz"}
        </button>
        {error ? <p role="alert" style={styles.muted}>{error}</p> : null}
      </div>
    );
  }

  return (
    <section aria-label="Post-class quiz" data-testid="post-class-quiz-panel" style={styles.block}>
      <h2 style={styles.blockHeading}>Post-class quiz</h2>
      {body()}
      {historyLine}
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
  // Authoritative score is persisted server-side on complete; this is the displayed value derived from
  // the refreshed attempt's per-question answers.
  const correct = qs.filter((q) => q.answer?.isCorrect).length;
  return Math.round((correct / total) * 100 * 100) / 100;
}

const styles = {
  block: {
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    display: "grid",
    gap: 12,
    padding: 16,
  },
  blockHeading: {
    color: "var(--color-text)", fontSize: 13, fontWeight: 600, letterSpacing: 0, margin: 0,
    textTransform: "uppercase",
  },
  startBlock: { display: "grid", gap: 10, justifyItems: "start" },
  questions: { display: "grid", gap: 14 },
  failed: { display: "grid", gap: 10, justifyItems: "start" },
  bodyText: { color: "var(--color-text)", fontSize: 14, lineHeight: 1.5, margin: 0 },
  muted: { color: "var(--color-text-muted)", fontSize: 14, fontStyle: "italic", margin: 0 },
  history: { color: "var(--color-text-muted)", fontSize: 13, margin: 0 },
  primaryButton: {
    background: "var(--color-primary)", border: "1px solid var(--color-primary)", borderRadius: 999, color: "var(--color-on-primary)",
    cursor: "pointer", fontSize: 13, fontWeight: 700, minHeight: 34, padding: "0 14px",
  },
} satisfies Record<string, React.CSSProperties>;
