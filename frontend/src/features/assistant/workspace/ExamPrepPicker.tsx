"use client";

/**
 * Exam-prep mode entry picker (Stage 8.6b). The student picks a MODULE (single enrolled module auto-
 * selected), then a NAMED AssessmentScope (Midterm/Final/…) whose covered weeks are shown read-only (UX
 * #2). Starting opens (or resumes) the exam_prep conversation bound to that scope and routes to it. The
 * scope list (incl. its quiz availability) comes from the existing quiz endpoint — the assistant never
 * generates a quiz. Inline idiom.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { type ExamPrepScopeSummary, type ModuleSummary } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { useAssistantStore } from "../AssistantStoreProvider";

export function ExamPrepPicker({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const store = useAssistantStore();
  const [modules, setModules] = useState<ModuleSummary[] | null>(null);
  const [modulesError, setModulesError] = useState(false);
  const [activeModuleId, setActiveModuleId] = useState<string | null>(null);
  const [scopes, setScopes] = useState<ExamPrepScopeSummary[] | null>(null);
  const [scopesState, setScopesState] = useState<"idle" | "loading" | "loaded" | "error">("idle");
  const [startingId, setStartingId] = useState<string | null>(null);
  const [startError, setStartError] = useState(false);

  const loadScopes = useCallback(async (moduleId: string) => {
    setActiveModuleId(moduleId);
    setScopesState("loading");
    setScopes(null);
    try {
      setScopes(await api.quiz.listExamPrepScopes(moduleId));
      setScopesState("loaded");
    } catch {
      setScopesState("error");
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const list = await api.modules.list();
        if (!mounted) return;
        setModules(list);
        if (list.length === 1) void loadScopes(list[0].id); // UX #1: single module auto-selected
      } catch {
        if (mounted) setModulesError(true);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [loadScopes]);

  const start = useCallback(
    async (scope: ExamPrepScopeSummary) => {
      setStartingId(scope.id);
      setStartError(false);
      try {
        const id = await store.ensureOpenForMode("exam_prep", { assessmentScopeId: scope.id });
        router.push(`/student/assistant/${id}`);
      } catch {
        setStartError(true);
        setStartingId(null);
      }
    },
    [store, router],
  );

  return (
    <div data-testid="assistant-examprep-picker" style={styles.panel}>
      <div style={styles.headerRow}>
        <h2 style={styles.heading}>Exam prep</h2>
        <button type="button" onClick={onClose} style={styles.linkButton}>
          Close
        </button>
      </div>
      <p style={styles.intro}>
        Pick a named exam. The assistant reviews exactly what it covers and helps you prioritise — it points
        you to the practice quiz but never makes one.
      </p>

      {modulesError ? (
        <p role="alert" style={styles.muted}>Couldn’t load your modules — try again.</p>
      ) : modules === null ? (
        <p style={styles.muted}>Loading your modules…</p>
      ) : modules.length === 0 ? (
        <p style={styles.muted}>No modules assigned.</p>
      ) : (
        <div style={styles.modules}>
          {modules.map((m) => (
            <button
              key={m.id}
              type="button"
              data-testid="assistant-examprep-module"
              onClick={() => void loadScopes(m.id)}
              style={m.id === activeModuleId ? styles.moduleActive : styles.module}
            >
              {m.title}
            </button>
          ))}
        </div>
      )}

      {activeModuleId ? (
        scopesState === "loading" ? (
          <p style={styles.muted}>Loading exams…</p>
        ) : scopesState === "error" ? (
          <p role="alert" style={styles.muted}>Couldn’t load exams — try again.</p>
        ) : scopes && scopes.length === 0 ? (
          <p style={styles.muted} data-testid="assistant-examprep-empty">No exams defined for this module yet.</p>
        ) : scopes ? (
          <ul style={styles.scopeList}>
            {scopes.map((s) => (
              <li key={s.id} style={styles.scopeRow} data-testid="assistant-examprep-scope">
                <span style={styles.scopeTitle}>
                  {s.name}{" "}
                  <span style={styles.scopeWeeks}>
                    · weeks {s.coveredWeeks.length ? s.coveredWeeks.join(", ") : "—"}
                  </span>
                </span>
                <button
                  type="button"
                  data-testid="assistant-examprep-start"
                  disabled={startingId === s.id}
                  onClick={() => void start(s)}
                  style={styles.startButton}
                >
                  {startingId === s.id ? "Opening…" : "Start"}
                </button>
              </li>
            ))}
          </ul>
        ) : null
      ) : null}
      {startError ? (
        <p role="alert" style={styles.muted}>Couldn’t start exam prep — try again.</p>
      ) : null}
    </div>
  );
}

const styles = {
  panel: { border: "1px solid #d7dde8", borderRadius: 8, display: "grid", gap: 12, padding: 16 },
  headerRow: { alignItems: "center", display: "flex", justifyContent: "space-between" },
  heading: { color: "#111827", fontSize: 14, fontWeight: 700, margin: 0, textTransform: "uppercase", letterSpacing: "0.03em" },
  linkButton: { background: "none", border: "none", color: "#174a63", cursor: "pointer", fontSize: 13, fontWeight: 600, padding: 0 },
  intro: { color: "#4b5563", fontSize: 13, lineHeight: 1.5, margin: 0 },
  modules: { display: "flex", flexWrap: "wrap", gap: 8 },
  module: {
    background: "#ffffff", border: "1px solid #d7dde8", borderRadius: 9999, color: "#374151",
    cursor: "pointer", fontSize: 13, padding: "6px 12px",
  },
  moduleActive: {
    background: "#174a63", border: "1px solid #174a63", borderRadius: 9999, color: "#ffffff",
    cursor: "pointer", fontSize: 13, padding: "6px 12px",
  },
  scopeList: { display: "grid", gap: 0, listStyle: "none", margin: 0, padding: 0 },
  scopeRow: {
    alignItems: "center", borderTop: "1px solid #e5e7eb", display: "flex", gap: 12,
    justifyContent: "space-between", padding: "10px 2px",
  },
  scopeTitle: { color: "#111827", fontSize: 14 },
  scopeWeeks: { color: "#6b7280", fontSize: 12 },
  startButton: {
    background: "#174a63", border: "1px solid #174a63", borderRadius: 6, color: "#ffffff",
    cursor: "pointer", fontSize: 12, fontWeight: 700, minHeight: 28, padding: "0 12px",
  },
  muted: { color: "#4b5563", fontSize: 14, fontStyle: "italic", margin: 0 },
} satisfies Record<string, React.CSSProperties>;
