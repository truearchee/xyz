"use client";

import { useEffect, useState } from "react";

import type { SectionMetadataPatchRequest } from "../../../lib/api";

type SectionMetadataEditorProps = {
  disabled?: boolean;
  dueAt: string | null;
  errorMessage: string | null;
  isSaving: boolean;
  onSave: (payload: SectionMetadataPatchRequest) => Promise<void>;
  sectionTitle: string;
  sectionType: string;
  sessionDate: string | null;
  weekNumber: number | null;
};

export function SectionMetadataEditor({
  disabled = false,
  dueAt,
  errorMessage,
  isSaving,
  onSave,
  sectionTitle,
  sectionType,
  sessionDate,
  weekNumber,
}: SectionMetadataEditorProps) {
  const [draftWeek, setDraftWeek] = useState(weekNumber?.toString() ?? "");
  const [draftDate, setDraftDate] = useState(sessionDate ?? "");
  const [draftDueAt, setDraftDueAt] = useState(toDateTimeLocal(dueAt));

  useEffect(() => {
    setDraftWeek(weekNumber?.toString() ?? "");
    setDraftDate(sessionDate ?? "");
    setDraftDueAt(toDateTimeLocal(dueAt));
  }, [dueAt, sessionDate, weekNumber]);

  const locked = disabled || isSaving;
  const key = sectionTitle
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

  return (
    <section aria-label={`Metadata for ${sectionTitle}`} data-testid={`section-metadata-editor-${key}`} style={styles.shell}>
      <div style={styles.fields}>
        <label style={styles.label}>
          Week
          <input
            aria-label={`Week number for ${sectionTitle}`}
            min={1}
            onChange={(event) => setDraftWeek(event.target.value)}
            style={styles.input}
            type="number"
            value={draftWeek}
          />
        </label>
        <button
          disabled={locked || !draftWeek}
          onClick={() => onSave({ weekNumber: Number(draftWeek) })}
          type="button"
        >
          {isSaving ? "Saving..." : "Save week"}
        </button>
        <label style={styles.label}>
          Date
          <input
            aria-label={`Session date for ${sectionTitle}`}
            onChange={(event) => setDraftDate(event.target.value)}
            style={styles.input}
            type="date"
            value={draftDate}
          />
        </label>
        <button
          disabled={locked || !draftDate}
          onClick={() => onSave({ sessionDate: draftDate })}
          type="button"
        >
          {isSaving ? "Saving..." : "Save date"}
        </button>
        {sectionType === "lab" ? (
          <>
            <label style={styles.label}>
              Due
              <input
                aria-label={`Due date for ${sectionTitle}`}
                onChange={(event) => setDraftDueAt(event.target.value)}
                style={styles.input}
                type="datetime-local"
                value={draftDueAt}
              />
            </label>
            <button
              disabled={locked}
              onClick={() => onSave({ dueAt: draftDueAt ? new Date(draftDueAt).toISOString() : null })}
              type="button"
            >
              {isSaving ? "Saving..." : "Save due"}
            </button>
          </>
        ) : null}
      </div>
      <p data-testid={`section-metadata-current-${key}`} style={styles.current}>
        Week {weekNumber ?? "unstamped"} · {sessionDate ?? "no date"}
        {sectionType === "lab" ? ` · ${dueAt ? formatDateTime(dueAt) : "No deadline set"}` : ""}
      </p>
      {errorMessage ? <p role="alert" style={styles.error}>{errorMessage}</p> : null}
    </section>
  );
}

function toDateTimeLocal(value: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const pad = (part: number) => part.toString().padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

const styles = {
  current: {
    color: "#374151",
    fontSize: 13,
    margin: 0,
  },
  error: {
    background: "#fef2f2",
    border: "1px solid #fecaca",
    borderRadius: 6,
    color: "#7f1d1d",
    fontSize: 13,
    lineHeight: 1.4,
    margin: 0,
    padding: "7px 9px",
  },
  fields: {
    alignItems: "end",
    display: "grid",
    gap: 8,
    gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
  },
  input: {
    border: "1px solid #cbd5e1",
    borderRadius: 6,
    fontSize: 13,
    minHeight: 34,
    padding: "5px 7px",
  },
  label: {
    color: "#374151",
    display: "grid",
    fontSize: 12,
    fontWeight: 700,
    gap: 4,
  },
  shell: {
    borderTop: "1px solid #e5e7eb",
    display: "grid",
    gap: 8,
    paddingTop: 14,
  },
} satisfies Record<string, React.CSSProperties>;
