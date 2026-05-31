"use client";

import { useEffect, useState } from "react";

import type { SectionDetail } from "../../lib/api/models/SectionDetail";

type LecturerNotesEditorProps = {
  disabled?: boolean;
  errorMessage?: string | null;
  onSave: (lecturerNotes: string | null) => void;
  section: SectionDetail;
};

export function LecturerNotesEditor({
  disabled = false,
  errorMessage = null,
  onSave,
  section,
}: LecturerNotesEditorProps) {
  const [draft, setDraft] = useState(section.lecturerNotes ?? "");

  useEffect(() => {
    setDraft(section.lecturerNotes ?? "");
  }, [section.id, section.lecturerNotes]);

  const savedNotes = section.lecturerNotes;

  return (
    <section aria-label="Lecturer notes" style={styles.shell}>
      <div style={styles.header}>
        <h2 style={styles.title}>Lecturer notes</h2>
        <button
          disabled={disabled}
          onClick={() => onSave(draft)}
          style={styles.button}
          type="button"
        >
          Save notes
        </button>
      </div>
      <textarea
        aria-label="Lecturer notes"
        disabled={disabled}
        onChange={(event) => setDraft(event.currentTarget.value)}
        rows={6}
        style={styles.textarea}
        value={draft}
      />
      <div aria-label="Saved lecturer notes" style={styles.preview}>
        {savedNotes ? savedNotes : "No notes saved"}
      </div>
      {errorMessage ? <p style={styles.error}>{errorMessage}</p> : null}
    </section>
  );
}

const styles = {
  shell: {
    display: "grid",
    gap: 10,
  },
  header: {
    alignItems: "center",
    display: "flex",
    gap: 10,
    justifyContent: "space-between",
  },
  title: {
    color: "#111827",
    fontSize: 16,
    lineHeight: 1.2,
    margin: 0,
  },
  button: {
    background: "#174a63",
    border: "1px solid #174a63",
    borderRadius: 6,
    color: "#ffffff",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 700,
    minHeight: 38,
    padding: "0 14px",
  },
  textarea: {
    border: "1px solid #d7dde8",
    borderRadius: 6,
    color: "#111827",
    font: "inherit",
    minHeight: 130,
    padding: 10,
    resize: "vertical",
    width: "100%",
  },
  preview: {
    border: "1px solid #e5e7eb",
    borderRadius: 6,
    color: "#374151",
    fontSize: 14,
    minHeight: 42,
    padding: 10,
    whiteSpace: "pre-wrap",
  },
  error: {
    color: "#b42318",
    fontSize: 13,
    margin: 0,
  },
} satisfies Record<string, React.CSSProperties>;
