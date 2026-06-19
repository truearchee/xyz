"use client";

/**
 * New-chat lecture picker (Stage 8.4). Lists the student's modules; selecting one lists its published
 * lecture/lab sections with their assistant-readiness state (Available / Disabled=processing /
 * Unavailable=no transcript; Hidden sections simply aren't returned by the visibility-gated list). Start
 * opens that lecture's grounded conversation (get-or-create) and routes to it. Inline idiom.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { type ModuleSummary, type StudentSectionListItem } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { useAssistantStore } from "../AssistantStoreProvider";
import { assistantReadinessFromError } from "../readiness";

type Availability = "ready" | "processing" | "unavailable";
const SECTION_TYPES = new Set(["lecture", "lab"]);

export function LecturePicker({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const store = useAssistantStore();
  const [modules, setModules] = useState<ModuleSummary[] | null>(null);
  const [modulesError, setModulesError] = useState(false);
  const [activeModuleId, setActiveModuleId] = useState<string | null>(null);
  const [sections, setSections] = useState<StudentSectionListItem[] | null>(null);
  const [availability, setAvailability] = useState<Record<string, Availability>>({});
  const [sectionsState, setSectionsState] = useState<"idle" | "loading" | "loaded" | "error">("idle");
  const [startingId, setStartingId] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const list = await api.modules.list();
        if (mounted) setModules(list);
      } catch {
        if (mounted) setModulesError(true);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const selectModule = useCallback(async (moduleId: string) => {
    setActiveModuleId(moduleId);
    setSectionsState("loading");
    setSections(null);
    setAvailability({});
    try {
      const all = await api.studentSummaries.listSections(moduleId);
      const lectures = all.filter((s) => SECTION_TYPES.has(s.type));
      setSections(lectures);
      setSectionsState("loaded");
      const entries = await Promise.all(
        lectures.map(async (s): Promise<[string, Availability]> => {
          try {
            const res = await api.assistant.getAvailability(s.id);
            return [s.id, (res.state as Availability) ?? "unavailable"];
          } catch (caught) {
            return [s.id, assistantReadinessFromError(caught) ?? "unavailable"];
          }
        }),
      );
      setAvailability(Object.fromEntries(entries));
    } catch {
      setSectionsState("error");
    }
  }, []);

  const start = useCallback(
    async (sectionId: string) => {
      setStartingId(sectionId);
      try {
        const id = await store.ensureOpenForSection(sectionId);
        router.push(`/student/assistant/${id}`);
      } catch (caught) {
        const readiness = assistantReadinessFromError(caught);
        if (readiness) {
          setAvailability((prev) => ({ ...prev, [sectionId]: readiness }));
        }
        setStartingId(null);
      }
    },
    [store, router],
  );

  return (
    <div data-testid="assistant-lecture-picker" style={styles.panel}>
      <div style={styles.headerRow}>
        <h2 style={styles.heading}>Start a chat from a lecture</h2>
        <button type="button" onClick={onClose} style={styles.linkButton}>
          Close
        </button>
      </div>

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
              data-testid="assistant-picker-module"
              onClick={() => void selectModule(m.id)}
              style={m.id === activeModuleId ? styles.moduleActive : styles.module}
            >
              {m.title}
            </button>
          ))}
        </div>
      )}

      {activeModuleId ? (
        sectionsState === "loading" ? (
          <p style={styles.muted}>Loading lectures…</p>
        ) : sectionsState === "error" ? (
          <p role="alert" style={styles.muted}>Couldn’t load lectures — try again.</p>
        ) : sections && sections.length === 0 ? (
          <p style={styles.muted}>No published lectures yet.</p>
        ) : sections ? (
          <ul style={styles.sectionList}>
            {sections.map((s) => {
              const state = availability[s.id];
              const available = state === "ready";
              return (
                <li key={s.id} style={styles.sectionRow} data-testid="assistant-picker-section" data-state={state ?? "loading"}>
                  <span style={styles.sectionTitle}>
                    {s.title} <span style={styles.sectionType}>· {s.type}</span>
                  </span>
                  {available ? (
                    <button
                      type="button"
                      data-testid="assistant-picker-start"
                      disabled={startingId === s.id}
                      onClick={() => void start(s.id)}
                      style={styles.startButton}
                    >
                      {startingId === s.id ? "Opening…" : "Start"}
                    </button>
                  ) : (
                    <span style={styles.sectionState}>
                      {state === "processing" ? "Processing…" : state === undefined ? "Checking…" : "No transcript yet"}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        ) : null
      ) : null}
    </div>
  );
}

const styles = {
  panel: { border: "1px solid #d7dde8", borderRadius: 8, display: "grid", gap: 12, padding: 16 },
  headerRow: { alignItems: "center", display: "flex", justifyContent: "space-between" },
  heading: { color: "#111827", fontSize: 14, fontWeight: 700, margin: 0, textTransform: "uppercase", letterSpacing: "0.03em" },
  linkButton: { background: "none", border: "none", color: "#174a63", cursor: "pointer", fontSize: 13, fontWeight: 600, padding: 0 },
  modules: { display: "flex", flexWrap: "wrap", gap: 8 },
  module: {
    background: "#ffffff", border: "1px solid #d7dde8", borderRadius: 9999, color: "#374151",
    cursor: "pointer", fontSize: 13, padding: "6px 12px",
  },
  moduleActive: {
    background: "#174a63", border: "1px solid #174a63", borderRadius: 9999, color: "#ffffff",
    cursor: "pointer", fontSize: 13, padding: "6px 12px",
  },
  sectionList: { display: "grid", gap: 0, listStyle: "none", margin: 0, padding: 0 },
  sectionRow: {
    alignItems: "center", borderTop: "1px solid #e5e7eb", display: "flex", gap: 12,
    justifyContent: "space-between", padding: "10px 2px",
  },
  sectionTitle: { color: "#111827", fontSize: 14 },
  sectionType: { color: "#6b7280", fontSize: 12 },
  sectionState: { color: "#6b7280", fontSize: 12, fontStyle: "italic" },
  startButton: {
    background: "#174a63", border: "1px solid #174a63", borderRadius: 6, color: "#ffffff",
    cursor: "pointer", fontSize: 12, fontWeight: 700, minHeight: 30, padding: "0 12px",
  },
  muted: { color: "#4b5563", fontSize: 14, fontStyle: "italic", margin: 0 },
} satisfies Record<string, React.CSSProperties>;
