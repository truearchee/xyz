"use client";

import { useCallback, useEffect, useState } from "react";

import {
  type ModuleSummary,
  type PracticeAvailability,
  type PracticeResult,
  type PracticeSessionState,
  StartPracticeRequest,
} from "../../lib/api";
import { api } from "../../lib/api/wrapper";
import { FlashcardsSession } from "./FlashcardsSession";
import { MultipleChoiceSession } from "./MultipleChoiceSession";

type Phase = "setup" | "running" | "result";
type Scope = "course" | "all";
type Mode = "flashcard" | "multiple_choice";

// Stage 7b/7c: the practice launcher + runner. Scope = a specific course or all saved terms; mode =
// Flashcards or Multiple-Choice. Multiple-Choice needs ≥4 in-scope terms (else only Flashcards).

export function PracticePage() {
  const [modules, setModules] = useState<ModuleSummary[]>([]);
  const [scope, setScope] = useState<Scope>("all");
  const [subjectId, setSubjectId] = useState("");
  const [mode, setMode] = useState<Mode>("flashcard");
  const [availability, setAvailability] = useState<PracticeAvailability | null>(null);
  const [phase, setPhase] = useState<Phase>("setup");
  const [session, setSession] = useState<PracticeSessionState | null>(null);
  const [result, setResult] = useState<PracticeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.modules
      .list()
      .then((m) => {
        setModules(m);
        if (m.length > 0) setSubjectId(m[0].id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (scope === "course" && !subjectId) {
      setAvailability(null);
      return;
    }
    let active = true;
    void api.glossary.practice
      .availability(mode, scope, scope === "course" ? subjectId : undefined)
      .then((a) => {
        if (active) setAvailability(a);
      })
      .catch(() => {
        if (active) setAvailability(null);
      });
    return () => {
      active = false;
    };
  }, [scope, mode, subjectId]);

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const s = await api.glossary.practice.start({
        scope:
          scope === "course"
            ? StartPracticeRequest.scope.COURSE
            : StartPracticeRequest.scope.ALL,
        subjectId: scope === "course" ? subjectId : null,
        mode:
          mode === "flashcard"
            ? StartPracticeRequest.mode.FLASHCARD
            : StartPracticeRequest.mode.MULTIPLE_CHOICE,
      });
      setSession(s);
      setPhase("running");
    } catch {
      setError("Couldn’t start — Multiple-Choice needs at least 4 saved terms in scope.");
    } finally {
      setBusy(false);
    }
  }, [scope, subjectId, mode]);

  const onAnswerFlash = useCallback(
    async (entryId: string, outcome: "known" | "not_known") => {
      if (session) await api.glossary.practice.answer(session.sessionId, { entryId, outcome });
    },
    [session],
  );

  const onAnswerMcq = useCallback(
    async (entryId: string, selectedEntryId: string | null) => {
      if (!session) return { isCorrect: null, correctEntryId: null };
      const fb = await api.glossary.practice.answer(session.sessionId, { entryId, selectedEntryId });
      return { isCorrect: fb.isCorrect, correctEntryId: fb.correctEntryId };
    },
    [session],
  );

  const finish = useCallback(async () => {
    if (!session) return;
    const r = await api.glossary.practice.complete(session.sessionId);
    setResult(r);
    setPhase("result");
  }, [session]);

  if (phase === "running" && session) {
    return (
      <section data-testid="glossary-practice-page" style={styles.shell}>
        <h1 style={styles.title}>Practice</h1>
        {session.mode === "flashcard" ? (
          <FlashcardsSession session={session} onAnswer={onAnswerFlash} onComplete={finish} />
        ) : (
          <MultipleChoiceSession session={session} onAnswer={onAnswerMcq} onComplete={finish} />
        )}
      </section>
    );
  }

  if (phase === "result" && result) {
    return (
      <section data-testid="glossary-practice-page" style={styles.shell}>
        <h1 style={styles.title}>Practice complete</h1>
        <div data-testid="glossary-practice-result" style={styles.result}>
          <p style={styles.resultLine}>Reviewed: {result.totalCount ?? 0}</p>
          <p style={styles.resultLine}>Known / correct: {result.correctCount ?? 0}</p>
          <p style={styles.resultLine}>Not known: {result.notKnownCount ?? 0}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setResult(null);
            setSession(null);
            setPhase("setup");
          }}
          style={styles.primary}
        >
          Practice again
        </button>
      </section>
    );
  }

  const mcqBlocked = mode === "multiple_choice" && availability != null && !availability.available;

  return (
    <section data-testid="glossary-practice-page" style={styles.shell}>
      <h1 style={styles.title}>Practice</h1>

      <fieldset style={styles.fieldset}>
        <legend style={styles.legend}>Scope</legend>
        <label style={styles.radio}>
          <input
            type="radio"
            name="scope"
            checked={scope === "all"}
            onChange={() => setScope("all")}
          />
          All my saved terms
        </label>
        <label style={styles.radio}>
          <input
            type="radio"
            name="scope"
            checked={scope === "course"}
            onChange={() => setScope("course")}
          />
          A specific course
        </label>
        {scope === "course" ? (
          <select
            data-testid="practice-course"
            value={subjectId}
            onChange={(e) => setSubjectId(e.target.value)}
            style={styles.input}
          >
            {modules.map((m) => (
              <option key={m.id} value={m.id}>
                {m.title}
              </option>
            ))}
          </select>
        ) : null}
      </fieldset>

      <fieldset style={styles.fieldset}>
        <legend style={styles.legend}>Mode</legend>
        <label style={styles.radio}>
          <input
            type="radio"
            name="mode"
            data-testid="practice-mode-flashcard"
            checked={mode === "flashcard"}
            onChange={() => setMode("flashcard")}
          />
          Flashcards
        </label>
        <label style={styles.radio}>
          <input
            type="radio"
            name="mode"
            data-testid="practice-mode-mcq"
            checked={mode === "multiple_choice"}
            onChange={() => setMode("multiple_choice")}
          />
          Multiple-Choice
        </label>
      </fieldset>

      {availability ? (
        <p data-testid="practice-availability" style={styles.muted}>
          {availability.termCount} term(s) in scope.
          {mcqBlocked ? " Multiple-Choice needs at least 4 — try Flashcards." : ""}
        </p>
      ) : null}
      {error ? (
        <p role="alert" style={styles.error}>
          {error}
        </p>
      ) : null}

      <button
        type="button"
        data-testid="practice-start"
        disabled={busy || !availability?.available}
        onClick={() => void start()}
        style={styles.primary}
      >
        {busy ? "Starting…" : "Start practice"}
      </button>
    </section>
  );
}

const styles = {
  shell: { display: "grid", gap: 16, maxWidth: 560 },
  title: { color: "#111827", fontSize: 24, margin: 0 },
  fieldset: { border: "1px solid #d7dde8", borderRadius: 8, display: "grid", gap: 8, padding: 12 },
  legend: { color: "#4b5563", fontSize: 12, fontWeight: 700, padding: "0 6px", textTransform: "uppercase" },
  radio: { alignItems: "center", color: "#111827", display: "flex", fontSize: 14, gap: 8 },
  input: { border: "1px solid #d7dde8", borderRadius: 6, fontSize: 14, minHeight: 36, padding: "0 10px" },
  muted: { color: "#4b5563", fontSize: 14, margin: 0 },
  error: { color: "#7f1d1d", fontSize: 14, margin: 0 },
  result: { border: "1px solid #d7dde8", borderRadius: 8, display: "grid", gap: 6, padding: 16 },
  resultLine: { color: "#111827", fontSize: 15, margin: 0 },
  primary: {
    background: "#174a63",
    border: "1px solid #174a63",
    borderRadius: 6,
    color: "#ffffff",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 700,
    justifySelf: "start",
    minHeight: 38,
    padding: "0 18px",
  },
} satisfies Record<string, React.CSSProperties>;
