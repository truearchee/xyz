"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  type StudentSectionRead,
  type StudentSectionSummariesRead,
  type StudentSummarySlot,
} from "../../../lib/api";
import { ForbiddenError, api } from "../../../lib/api/wrapper";
import { PostClassQuizPanel } from "../../quiz/PostClassQuizPanel";
import { StudentAssetRow } from "./StudentAssetRow";
import { SummaryMarkdown } from "./SummaryMarkdown";

// Reuse the 4.5d backoff (no hard timeout), narrowed to the student summary sub-resource and bounded to
// the `generating` state (§11). A generous wall-clock ceiling — detailed via K2-Think is legitimately
// slow — after which we stop and ask the student to refresh (§10).
const POLL_INITIAL_MS = 1500;
const POLL_MAX_MS = 15_000;
const POLL_BACKOFF = 1.5;
const POLL_WALLCLOCK_CAP_MS = 8 * 60_000;

const GENERATING = "generating";
const READY = "ready";
const UNAVAILABLE = "unavailable";
const NOT_APPLICABLE = "not_applicable";

type ShellState = "loading" | "loaded" | "missing" | "error";

export function StudentSectionDetail({ moduleId, sectionId }: { moduleId: string; sectionId: string }) {
  const [section, setSection] = useState<StudentSectionRead | null>(null);
  const [shellState, setShellState] = useState<ShellState>("loading");

  useEffect(() => {
    let mounted = true;
    setShellState("loading");
    setSection(null);
    void (async () => {
      try {
        const detail = await api.studentSummaries.getSection(sectionId);
        if (!mounted) return;
        setSection(detail);
        setShellState("loaded");
      } catch (caught) {
        if (!mounted) return;
        // 404 (rows D/P/I) and 403 are both "you cannot see this" — never leak which.
        if (caught instanceof ForbiddenError || (caught instanceof ApiError && caught.status === 404)) {
          setShellState("missing");
        } else {
          setShellState("error");
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, [sectionId]);

  if (shellState === "loading") {
    return (
      <section aria-busy="true" style={styles.panel}>
        <h1 style={styles.stateTitle}>Loading section…</h1>
      </section>
    );
  }
  if (shellState === "missing") {
    return (
      <section aria-label="Section unavailable" style={styles.panel}>
        <h1 style={styles.stateTitle}>This section is unavailable</h1>
        <p style={styles.stateText}>It may be unpublished or you may not have access.</p>
      </section>
    );
  }
  if (shellState === "error" || section === null) {
    return (
      <section role="alert" style={styles.errorPanel}>
        <h1 style={styles.stateTitle}>Couldn’t load this section</h1>
        <p style={styles.stateText}>Please refresh to try again.</p>
      </section>
    );
  }

  return (
    <section aria-labelledby="student-section-title" data-testid="student-section-detail" style={styles.shell}>
      <header>
        <p style={styles.eyebrow}>{section.type}</p>
        <h1 id="student-section-title" style={styles.title}>
          {section.title}
        </h1>
      </header>

      <section aria-label="Lecturer notes" style={styles.block}>
        <h2 style={styles.blockHeading}>Lecturer notes</h2>
        {section.lecturerNotes ? (
          <p style={styles.bodyText}>{section.lecturerNotes}</p>
        ) : (
          <p style={styles.muted}>No lecturer notes</p>
        )}
      </section>

      {section.type === "lab" ? (
        <section aria-label="Deadline" style={styles.block}>
          <h2 style={styles.blockHeading}>Deadline</h2>
          <p data-testid={`student-section-detail-due-at-${section.id}`} style={styles.bodyText}>
            {section.dueAt ? formatDateTime(section.dueAt) : "No deadline set"}
          </p>
        </section>
      ) : null}

      <section aria-label="Learning materials" style={styles.block}>
        <h2 style={styles.blockHeading}>Learning materials</h2>
        {section.materials.length === 0 ? (
          <p style={styles.muted}>No materials</p>
        ) : (
          <ul style={styles.materialList}>
            {section.materials.map((m) => (
              <StudentAssetRow
                asset={m}
                key={m.id}
                moduleId={moduleId}
                sectionId={section.id}
              />
            ))}
          </ul>
        )}
      </section>

      <SummariesPanel sectionId={sectionId} />

      <PostClassQuizPanel sectionId={sectionId} />
    </section>
  );
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function SummariesPanel({ sectionId }: { sectionId: string }) {
  const [summaries, setSummaries] = useState<StudentSectionSummariesRead | null>(null);
  const [readError, setReadError] = useState(false);
  const [capped, setCapped] = useState(false);
  const startedAt = useRef<number>(0);

  const renderedGenerating = useCallback((data: StudentSectionSummariesRead | null): boolean => {
    if (!data) return false;
    return data.summaries.brief.state === GENERATING || data.summaries.detailed.state === GENERATING;
  }, []);

  useEffect(() => {
    let mounted = true;
    let timeoutId = 0;
    let delay = POLL_INITIAL_MS;
    startedAt.current = 0;
    setSummaries(null);
    setReadError(false);
    setCapped(false);

    const tick = async (): Promise<void> => {
      try {
        const next = await api.studentSummaries.getSummaries(sectionId);
        if (!mounted) return;
        setSummaries(next);
        setReadError(false);
        if (!renderedGenerating(next)) {
          return; // all slots terminal — stop polling
        }
      } catch {
        if (!mounted) return;
        setReadError(true);
        // transient — keep polling with backoff
      }
      if (!mounted) return;
      // Wall-clock cap: detailed generation is legitimately slow; stop and ask for a refresh.
      if (startedAt.current === 0) {
        // first scheduled poll establishes the clock baseline (Date.now is fine in the browser)
        startedAt.current = Date.now();
      } else if (Date.now() - startedAt.current > POLL_WALLCLOCK_CAP_MS) {
        setCapped(true);
        return;
      }
      delay = Math.min(Math.round(delay * POLL_BACKOFF), POLL_MAX_MS);
      timeoutId = window.setTimeout(() => void tick(), delay);
    };

    void tick();
    return () => {
      mounted = false;
      window.clearTimeout(timeoutId); // no leaked intervals on unmount
    };
  }, [sectionId, renderedGenerating]);

  if (summaries === null) {
    return (
      <section aria-busy={!readError} aria-label="Summaries" style={styles.block}>
        <h2 style={styles.blockHeading}>Summaries</h2>
        {readError ? (
          <p role="alert" style={styles.muted}>
            Couldn’t load summaries — refresh to try again.
          </p>
        ) : (
          <p style={styles.muted}>Loading summaries…</p>
        )}
      </section>
    );
  }

  return (
    <section aria-label="Summaries" style={styles.block}>
      <SummarySlot label="Brief summary" testId="student-summary-brief" slot={summaries.summaries.brief} capped={capped} />
      <SummarySlot
        label="Detailed study summary"
        testId="student-summary-detailed"
        slot={summaries.summaries.detailed}
        capped={capped}
      />
    </section>
  );
}

function SummarySlot({
  label,
  testId,
  slot,
  capped,
}: {
  label: string;
  testId: string;
  slot: StudentSummarySlot;
  capped: boolean;
}) {
  if (slot.state === NOT_APPLICABLE) {
    return null; // block absent for non-lecture/lab
  }
  return (
    <div data-testid={testId} data-state={slot.state} style={styles.summaryBlock}>
      <h3 style={styles.summaryHeading}>{label}</h3>
      {slot.state === READY && slot.content ? (
        <SummaryMarkdown content={slot.content} testId={`${testId}-content`} />
      ) : slot.state === GENERATING ? (
        <p role="status" style={styles.muted}>
          {capped ? "Still being generated — refresh to check." : "Summary is being generated."}
        </p>
      ) : (
        <p role="status" style={styles.muted}>
          Summary is currently unavailable.
        </p>
      )}
    </div>
  );
}

const styles = {
  shell: { display: "grid", gap: 18 },
  panel: { border: "1px solid #d7dde8", borderRadius: 8, padding: 24 },
  errorPanel: { border: "1px solid #f0b4b4", borderRadius: 8, color: "#7f1d1d", padding: 24 },
  eyebrow: {
    color: "#4b5563",
    fontSize: 13,
    fontWeight: 700,
    margin: "0 0 4px",
    textTransform: "uppercase",
  },
  title: { color: "#111827", fontSize: 24, lineHeight: 1.2, margin: 0 },
  block: { border: "1px solid #d7dde8", borderRadius: 8, display: "grid", gap: 8, padding: 16 },
  blockHeading: {
    color: "#111827",
    fontSize: 13,
    fontWeight: 700,
    margin: 0,
    textTransform: "uppercase",
    letterSpacing: "0.03em",
  },
  summaryBlock: { display: "grid", gap: 6 },
  summaryHeading: { color: "#374151", fontSize: 14, fontWeight: 700, margin: 0 },
  bodyText: { color: "#111827", fontSize: 14, lineHeight: 1.5, margin: 0 },
  muted: { color: "#4b5563", fontSize: 14, fontStyle: "italic", margin: 0 },
  stateTitle: { fontSize: 18, lineHeight: 1.35, margin: 0 },
  stateText: { fontSize: 14, lineHeight: 1.5, margin: "8px 0 0" },
  materialList: { color: "#111827", display: "grid", gap: 8, listStyle: "none", margin: 0, padding: 0 },
} satisfies Record<string, React.CSSProperties>;
