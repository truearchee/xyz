"use client";

import Link from "next/link";
import type React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  type ExamPrepScopeSummary,
  type MistakeBankItem,
  type QuizAttemptForStudent,
  type RecapScopeRequest,
  type ScopeAvailabilityResponse,
  type StudentSectionDetail,
} from "../../lib/api";
import { api } from "../../lib/api/wrapper";
import { QuizAttemptPanel } from "./QuizAttemptPanel";

type Mode = "recap" | "exam" | "bank";

function parseWeeks(value: string): number[] {
  return value
    .split(",")
    .map((part) => Number(part.trim()))
    .filter((n) => Number.isInteger(n) && n > 0);
}

function apiMessage(caught: unknown): string {
  if (caught instanceof ApiError) {
    const detail = caught.body?.detail;
    if (typeof detail === "object" && detail !== null && "code" in detail) {
      return String((detail as { code: unknown }).code).replace(/_/g, " ");
    }
    if (typeof detail === "string") return detail;
    return caught.message;
  }
  if (caught instanceof Error) return caught.message;
  return "Unexpected error";
}

export function StudentQuizModesPanel({
  moduleId,
  sections,
}: {
  moduleId: string;
  sections: StudentSectionDetail[];
}) {
  const [activeMode, setActiveMode] = useState<Mode | null>(null);
  const [attempt, setAttempt] = useState<QuizAttemptForStudent | null>(null);
  const [attemptLabel, setAttemptLabel] = useState("Quiz");
  const [restart, setRestart] = useState<(() => Promise<QuizAttemptForStudent>) | null>(null);
  const postClassTarget = useMemo(
    () => sections.find((s) => s.type === "lecture" || s.type === "lab") ?? null,
    [sections],
  );

  const startAttempt = useCallback(
    async (label: string, starter: () => Promise<QuizAttemptForStudent>) => {
      const next = await starter();
      setAttempt(next);
      setAttemptLabel(label);
      setRestart(() => starter);
      setActiveMode(null);
    },
    [],
  );

  return (
    <section aria-label="Quiz modes" data-testid="quiz-mode-selector" style={styles.block}>
      <header style={styles.header}>
        <div>
          <h2 style={styles.heading}>Quizzes</h2>
          <p style={styles.muted}>Choose a practice mode for this module.</p>
        </div>
      </header>
      <div style={styles.modeGrid}>
        <ModeCard
          title="Post-class"
          detail={postClassTarget ? "Open a section quiz." : "No quiz-ready sections."}
          testId="quiz-mode-post-class"
          disabled={!postClassTarget}
        >
          {postClassTarget ? (
            <Link
              href={`/student/modules/${moduleId}/sections/${postClassTarget.id}`}
              style={styles.cardLink}
            >
              Open section
            </Link>
          ) : null}
        </ModeCard>
        <ModeCard title="Recap" detail="Practise by weeks or date range." testId="quiz-mode-recap">
          <button type="button" onClick={() => setActiveMode("recap")} style={styles.secondaryButton}>
            Choose scope
          </button>
        </ModeCard>
        <ModeCard title="Exam prep" detail="Use lecturer-defined covered weeks." testId="quiz-mode-exam-prep">
          <button type="button" onClick={() => setActiveMode("exam")} style={styles.secondaryButton}>
            Choose scope
          </button>
        </ModeCard>
        <ModeCard title="Mistakes bank" detail="Practise saved mistakes for this module." testId="quiz-mode-bank">
          <button type="button" onClick={() => setActiveMode("bank")} style={styles.secondaryButton}>
            Open bank
          </button>
        </ModeCard>
      </div>

      {attempt && restart ? (
        <QuizAttemptPanel attempt={attempt} label={attemptLabel} onStartOver={restart} />
      ) : null}

      {activeMode === "recap" ? (
        <RecapModal
          moduleId={moduleId}
          onClose={() => setActiveMode(null)}
          onStart={(payload) =>
            startAttempt("Recap quiz", () => api.quiz.startRecap(moduleId, payload))
          }
        />
      ) : null}
      {activeMode === "exam" ? (
        <ExamPrepModal
          moduleId={moduleId}
          onClose={() => setActiveMode(null)}
          onStart={(scope) =>
            startAttempt(`Exam prep: ${scope.name}`, () => api.quiz.startExamPrep(scope.id))
          }
        />
      ) : null}
      {activeMode === "bank" ? (
        <MistakesBankModal
          moduleId={moduleId}
          onClose={() => setActiveMode(null)}
          onStart={() =>
            startAttempt("Mistakes bank", () => api.quiz.startMistakesBank(moduleId))
          }
        />
      ) : null}
    </section>
  );
}

function ModeCard({
  children,
  detail,
  disabled = false,
  testId,
  title,
}: {
  children: React.ReactNode;
  detail: string;
  disabled?: boolean;
  testId: string;
  title: string;
}) {
  return (
    <div data-disabled={disabled} data-testid={testId} style={disabled ? styles.modeCardDisabled : styles.modeCard}>
      <div>
        <h3 style={styles.cardTitle}>{title}</h3>
        <p style={styles.cardText}>{detail}</p>
      </div>
      {children}
    </div>
  );
}

function RecapModal({
  moduleId,
  onClose,
  onStart,
}: {
  moduleId: string;
  onClose: () => void;
  onStart: (payload: RecapScopeRequest) => Promise<void>;
}) {
  const [weeks, setWeeks] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [availability, setAvailability] = useState<ScopeAvailabilityResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const payload = useMemo<RecapScopeRequest | null>(() => {
    const parsedWeeks = parseWeeks(weeks);
    if (parsedWeeks.length > 0) return { weeks: parsedWeeks };
    if (startDate && endDate) return { startDate, endDate };
    return null;
  }, [weeks, startDate, endDate]);

  async function checkAvailability() {
    if (!payload) {
      setError("Enter weeks or a date range.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setAvailability(await api.quiz.getRecapAvailability(moduleId, payload));
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    if (!payload) return;
    setBusy(true);
    setError(null);
    try {
      await onStart(payload);
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Recap scope" onClose={onClose} testId="quiz-recap-scope-modal">
      <label style={styles.label}>
        Weeks
        <input
          aria-label="Recap weeks"
          placeholder="1,2,3"
          value={weeks}
          onChange={(event) => {
            setWeeks(event.target.value);
            if (event.target.value) {
              setStartDate("");
              setEndDate("");
            }
            setAvailability(null);
          }}
          style={styles.input}
        />
      </label>
      <div style={styles.twoColumn}>
        <label style={styles.label}>
          Start date
          <input
            aria-label="Recap start date"
            type="date"
            value={startDate}
            onChange={(event) => {
              setStartDate(event.target.value);
              if (event.target.value) setWeeks("");
              setAvailability(null);
            }}
            style={styles.input}
          />
        </label>
        <label style={styles.label}>
          End date
          <input
            aria-label="Recap end date"
            type="date"
            value={endDate}
            onChange={(event) => {
              setEndDate(event.target.value);
              if (event.target.value) setWeeks("");
              setAvailability(null);
            }}
            style={styles.input}
          />
        </label>
      </div>
      <AvailabilityLine availability={availability} />
      {error ? <p role="alert" style={styles.errorText}>{error}</p> : null}
      <div style={styles.actions}>
        <button type="button" disabled={busy || !payload} onClick={() => void checkAvailability()} style={styles.secondaryButton}>
          {busy ? "Checking..." : "Check"}
        </button>
        <button
          type="button"
          disabled={busy || !payload || availability?.available === false}
          onClick={() => void start()}
          style={styles.primaryButton}
        >
          {busy ? "Starting..." : "Start recap"}
        </button>
      </div>
    </Modal>
  );
}

function ExamPrepModal({
  moduleId,
  onClose,
  onStart,
}: {
  moduleId: string;
  onClose: () => void;
  onStart: (scope: ExamPrepScopeSummary) => Promise<void>;
}) {
  const [scopes, setScopes] = useState<ExamPrepScopeSummary[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const next = await api.quiz.listExamPrepScopes(moduleId);
        if (mounted) setScopes(next);
      } catch (caught) {
        if (mounted) {
          setError(apiMessage(caught));
          setScopes([]);
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, [moduleId]);

  async function start(scope: ExamPrepScopeSummary) {
    setBusyId(scope.id);
    setError(null);
    try {
      await onStart(scope);
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Modal title="Exam-prep scope" onClose={onClose} testId="quiz-exam-scope-modal">
      {scopes === null ? <p style={styles.muted}>Loading scopes...</p> : null}
      {scopes?.length === 0 ? <EmptyState text="No exam-prep scopes yet." /> : null}
      {scopes && scopes.length > 0 ? (
        <div style={styles.list}>
          {scopes.map((scope) => (
            <div key={scope.id} style={styles.scopeRow}>
              <div>
                <strong>{scope.name}</strong>
                <p style={styles.cardText}>Weeks {scope.coveredWeeks.join(", ")}</p>
                <AvailabilityLine availability={scope} />
              </div>
              <button
                type="button"
                disabled={!scope.available || busyId === scope.id}
                onClick={() => void start(scope)}
                style={styles.primaryButton}
              >
                {busyId === scope.id ? "Starting..." : "Start"}
              </button>
            </div>
          ))}
        </div>
      ) : null}
      {error ? <p role="alert" style={styles.errorText}>{error}</p> : null}
    </Modal>
  );
}

function MistakesBankModal({
  moduleId,
  onClose,
  onStart,
}: {
  moduleId: string;
  onClose: () => void;
  onStart: () => Promise<void>;
}) {
  const [items, setItems] = useState<MistakeBankItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const page = await api.quiz.listMistakesBank(moduleId, 50, 0);
        if (mounted) {
          setItems(page.items);
          setTotal(page.pagination.total);
        }
      } catch (caught) {
        if (mounted) {
          setError(apiMessage(caught));
          setItems([]);
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, [moduleId]);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await onStart();
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Mistakes bank" onClose={onClose} testId="quiz-mistakes-bank-modal">
      {items === null ? <p style={styles.muted}>Loading mistakes...</p> : null}
      {items?.length === 0 ? <EmptyState text="No saved mistakes in this module." /> : null}
      {items && items.length > 0 ? (
        <>
          <p data-testid="quiz-mistakes-bank-count" style={styles.muted}>
            {total === 1 ? "1 saved mistake" : `${total} saved mistakes`}
          </p>
          <div style={styles.list}>
            {items.slice(0, 5).map((item) => (
              <div key={item.id} data-testid={`quiz-mistake-bank-item-${item.id}`} style={styles.bankRow}>
                <strong>{String(item.questionSnapshot.questionText ?? "Saved question")}</strong>
                <span style={styles.cardText}>Correct answer: {item.correctAnswer}</span>
              </div>
            ))}
          </div>
          <button type="button" disabled={busy} onClick={() => void start()} style={styles.primaryButton}>
            {busy ? "Starting..." : "Start mistakes bank"}
          </button>
        </>
      ) : null}
      {error ? <p role="alert" style={styles.errorText}>{error}</p> : null}
    </Modal>
  );
}

function AvailabilityLine({
  availability,
}: {
  availability: Pick<ScopeAvailabilityResponse, "available" | "reasonCode" | "readySectionCount" | "processingSectionCount"> | null;
}) {
  if (!availability) return null;
  if (availability.available) {
    return (
      <p role="status" style={styles.availableText}>
        Ready{availability.readySectionCount ? `: ${availability.readySectionCount} sections` : ""}
      </p>
    );
  }
  return (
    <p role="status" style={styles.waitingText}>
      {availability.reasonCode === "processing"
        ? `Waiting on ${availability.processingSectionCount ?? 0} sections`
        : "No eligible sections"}
    </p>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p data-testid="quiz-empty-state" style={styles.muted}>{text}</p>;
}

function Modal({
  children,
  onClose,
  testId,
  title,
}: {
  children: React.ReactNode;
  onClose: () => void;
  testId: string;
  title: string;
}) {
  return (
    <div role="presentation" style={styles.modalBackdrop}>
      <section role="dialog" aria-modal="true" aria-label={title} data-testid={testId} style={styles.modal}>
        <header style={styles.modalHeader}>
          <h2 style={styles.heading}>{title}</h2>
          <button type="button" aria-label="Close" onClick={onClose} style={styles.iconButton}>
            x
          </button>
        </header>
        <div style={styles.modalBody}>{children}</div>
      </section>
    </div>
  );
}

const cardBase = {
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-lg)",
  display: "grid",
  gap: 12,
  minHeight: 138,
  padding: 14,
} satisfies React.CSSProperties;

const styles = {
  block: {
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    display: "grid",
    gap: 14,
    padding: 16,
  },
  header: { alignItems: "flex-start", display: "flex", justifyContent: "space-between" },
  heading: { color: "var(--color-text)", fontSize: 18, lineHeight: 1.3, margin: 0 },
  modeGrid: {
    display: "grid",
    gap: 12,
    gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
  },
  modeCard: { ...cardBase, background: "var(--color-surface)" },
  modeCardDisabled: { ...cardBase, background: "var(--color-surface-muted)", color: "var(--color-text-muted)" },
  cardTitle: { color: "var(--color-text)", fontSize: 15, lineHeight: 1.3, margin: "0 0 4px" },
  cardText: { color: "var(--color-text-muted)", fontSize: 13, lineHeight: 1.4, margin: 0 },
  cardLink: { color: "var(--color-text)", fontSize: 13, fontWeight: 700, textDecoration: "none" },
  muted: { color: "var(--color-text-muted)", fontSize: 14, lineHeight: 1.5, margin: 0 },
  label: { color: "var(--color-text)", display: "grid", fontSize: 13, fontWeight: 600, gap: 6 },
  input: {
    background: "var(--color-surface)", border: "1px solid var(--color-border-strong)", borderRadius: "var(--radius-md)", color: "var(--color-text)", fontSize: 14,
    minHeight: 36, padding: "0 10px",
  },
  twoColumn: { display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" },
  actions: { display: "flex", flexWrap: "wrap", gap: 10 },
  primaryButton: {
    background: "var(--color-primary)", border: "1px solid var(--color-primary)", borderRadius: 999, color: "var(--color-on-primary)",
    cursor: "pointer", fontSize: 13, fontWeight: 700, minHeight: 34, padding: "0 14px",
  },
  secondaryButton: {
    background: "var(--color-surface)", border: "1px solid var(--color-border-strong)", borderRadius: 999, color: "var(--color-text)",
    cursor: "pointer", fontSize: 13, fontWeight: 700, minHeight: 34, padding: "0 14px",
  },
  iconButton: {
    background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 999, color: "var(--color-text)",
    cursor: "pointer", fontSize: 14, fontWeight: 700, height: 32, width: 32,
  },
  modalBackdrop: {
    alignItems: "center", background: "var(--color-overlay)", bottom: 0, display: "flex",
    justifyContent: "center", left: 0, padding: 16, position: "fixed", right: 0, top: 0, zIndex: 20,
  },
  modal: {
    background: "var(--color-surface)", borderRadius: "var(--radius-xl)", boxShadow: "var(--shadow-lg)",
    display: "grid", gap: 12, maxHeight: "88vh", maxWidth: 620, overflow: "auto", padding: 16, width: "100%",
  },
  modalHeader: { alignItems: "center", display: "flex", gap: 12, justifyContent: "space-between" },
  modalBody: { display: "grid", gap: 12 },
  availableText: { color: "var(--color-success-text)", fontSize: 13, fontWeight: 700, margin: 0 },
  waitingText: { color: "var(--color-warning-text)", fontSize: 13, fontWeight: 700, margin: 0 },
  errorText: { color: "var(--color-danger-text)", fontSize: 13, margin: 0 },
  list: { display: "grid", gap: 10 },
  scopeRow: {
    alignItems: "center", border: "1px solid var(--color-border)", borderRadius: "var(--radius-lg)", display: "flex",
    gap: 12, justifyContent: "space-between", padding: 12,
  },
  bankRow: { border: "1px solid var(--color-border)", borderRadius: "var(--radius-lg)", display: "grid", gap: 4, padding: 12 },
} satisfies Record<string, React.CSSProperties>;
