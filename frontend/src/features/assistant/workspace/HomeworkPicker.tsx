"use client";

/**
 * Homework-mode entry picker (Stage 8.6a). The student picks a MODULE (required per UX #1 — a single
 * enrolled module is auto-selected) and may optionally narrow to one lecture/lab for tighter context.
 * Starting opens (or resumes) the homework_help conversation for that binding and routes to it. Unlike
 * the LecturePicker it does NOT gate on transcript readiness — homework coaches even before lecture
 * material is processed (the answer is then general, never the final solution). Inline idiom.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { type ModuleSummary, type StudentSectionListItem } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { useAssistantStore } from "../AssistantStoreProvider";

const SECTION_TYPES = new Set(["lecture", "lab"]);

export function HomeworkPicker({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const store = useAssistantStore();
  const [modules, setModules] = useState<ModuleSummary[] | null>(null);
  const [modulesError, setModulesError] = useState(false);
  const [activeModuleId, setActiveModuleId] = useState<string | null>(null);
  const [sections, setSections] = useState<StudentSectionListItem[] | null>(null);
  const [sectionsState, setSectionsState] = useState<"idle" | "loading" | "loaded" | "error">("idle");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState(false);

  const loadSections = useCallback(async (moduleId: string) => {
    setActiveModuleId(moduleId);
    setSectionsState("loading");
    setSections(null);
    try {
      const all = await api.studentSummaries.listSections(moduleId);
      setSections(all.filter((s) => SECTION_TYPES.has(s.type)));
      setSectionsState("loaded");
    } catch {
      setSectionsState("error");
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const list = await api.modules.list();
        if (!mounted) return;
        setModules(list);
        if (list.length === 1) void loadSections(list[0].id); // UX #1: single module auto-selected
      } catch {
        if (mounted) setModulesError(true);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [loadSections]);

  const start = useCallback(
    async (moduleId: string, sectionId?: string) => {
      setStarting(true);
      setStartError(false);
      try {
        const id = await store.ensureOpenForMode("homework_help", { moduleId, sectionId });
        router.push(`/student/assistant/${id}`);
      } catch {
        setStartError(true);
        setStarting(false);
      }
    },
    [store, router],
  );

  return (
    <div data-testid="assistant-homework-picker" style={styles.panel}>
      <div style={styles.headerRow}>
        <h2 style={styles.heading}>Help with homework</h2>
        <button type="button" onClick={onClose} style={styles.linkButton}>
          Close
        </button>
      </div>
      <p style={styles.intro}>
        Pick the module your problem is from. The assistant coaches you with hints and questions — it never
        gives the final answer.
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
              data-testid="assistant-homework-module"
              onClick={() => void loadSections(m.id)}
              style={m.id === activeModuleId ? styles.moduleActive : styles.module}
            >
              {m.title}
            </button>
          ))}
        </div>
      )}

      {activeModuleId ? (
        <div style={styles.startBlock}>
          <button
            type="button"
            data-testid="assistant-homework-start"
            disabled={starting}
            onClick={() => void start(activeModuleId)}
            style={styles.startButton}
          >
            {starting ? "Opening…" : "Start homework help"}
          </button>
          <span style={styles.hint}>or focus on one lecture/lab (optional):</span>
          {sectionsState === "loading" ? (
            <p style={styles.muted}>Loading lectures…</p>
          ) : sectionsState === "error" ? (
            <p role="alert" style={styles.muted}>Couldn’t load lectures — you can still start with the whole module.</p>
          ) : sections && sections.length > 0 ? (
            <ul style={styles.sectionList}>
              {sections.map((s) => (
                <li key={s.id} style={styles.sectionRow} data-testid="assistant-homework-section">
                  <span style={styles.sectionTitle}>
                    {s.title} <span style={styles.sectionType}>· {s.type}</span>
                  </span>
                  <button
                    type="button"
                    data-testid="assistant-homework-section-start"
                    disabled={starting}
                    onClick={() => void start(activeModuleId, s.id)}
                    style={styles.sectionStart}
                  >
                    Focus on this
                  </button>
                </li>
              ))}
            </ul>
          ) : sections ? (
            <p style={styles.muted}>No published lectures yet — start with the whole module.</p>
          ) : null}
          {startError ? (
            <p role="alert" style={styles.muted}>Couldn’t start homework help — try again.</p>
          ) : null}
        </div>
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
  startBlock: { display: "grid", gap: 8 },
  hint: { color: "#6b7280", fontSize: 12 },
  sectionList: { display: "grid", gap: 0, listStyle: "none", margin: 0, padding: 0 },
  sectionRow: {
    alignItems: "center", borderTop: "1px solid #e5e7eb", display: "flex", gap: 12,
    justifyContent: "space-between", padding: "10px 2px",
  },
  sectionTitle: { color: "#111827", fontSize: 14 },
  sectionType: { color: "#6b7280", fontSize: 12 },
  startButton: {
    background: "#174a63", border: "1px solid #174a63", borderRadius: 6, color: "#ffffff",
    cursor: "pointer", fontSize: 13, fontWeight: 700, justifySelf: "start", minHeight: 32, padding: "0 14px",
  },
  sectionStart: {
    background: "#ffffff", border: "1px solid #174a63", borderRadius: 6, color: "#174a63",
    cursor: "pointer", fontSize: 12, fontWeight: 700, minHeight: 28, padding: "0 10px",
  },
  muted: { color: "#4b5563", fontSize: 14, fontStyle: "italic", margin: 0 },
} satisfies Record<string, React.CSSProperties>;
