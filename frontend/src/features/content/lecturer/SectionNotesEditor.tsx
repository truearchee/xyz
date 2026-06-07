"use client";

import { useEffect, useState } from "react";

type SectionNotesEditorProps = {
  disabled?: boolean;
  errorMessage?: string | null;
  initialNotes: string | null;
  isSaving?: boolean;
  onSave: (lecturerNotes: string | null) => Promise<void>;
  sectionTitle: string;
};

export function SectionNotesEditor({
  disabled = false,
  errorMessage = null,
  initialNotes,
  isSaving = false,
  onSave,
  sectionTitle,
}: SectionNotesEditorProps) {
  const [draft, setDraft] = useState(initialNotes ?? "");

  useEffect(() => {
    setDraft(initialNotes ?? "");
  }, [initialNotes]);

  const isDisabled = disabled || isSaving;

  return (
    <div style={styles.shell}>
      <label style={styles.label}>
        <span style={styles.labelText}>Lecturer notes</span>
        <textarea
          aria-label={`Lecturer notes for ${sectionTitle}`}
          disabled={isDisabled}
          onChange={(event) => setDraft(event.currentTarget.value)}
          rows={5}
          style={styles.textarea}
          value={draft}
        />
      </label>
      <div style={styles.actions}>
        <button
          disabled={isDisabled}
          onClick={() => onSave(draft.trim() ? draft : null)}
          style={styles.button}
          type="button"
        >
          {isSaving ? "Saving notes" : "Save notes"}
        </button>
        <p aria-live="polite" style={styles.persisted}>
          {initialNotes ? "Persisted notes loaded" : "No notes saved"}
        </p>
      </div>
      {errorMessage ? (
        <p role="alert" style={styles.error}>
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}

const styles = {
  shell: {
    display: "grid",
    gap: 10,
  },
  label: {
    display: "grid",
    gap: 6,
  },
  labelText: {
    color: "#374151",
    fontSize: 13,
    fontWeight: 700,
  },
  textarea: {
    border: "1px solid #cbd5e1",
    borderRadius: 6,
    color: "#111827",
    font: "inherit",
    minHeight: 118,
    padding: 10,
    resize: "vertical",
    width: "100%",
  },
  actions: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
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
  persisted: {
    color: "#4b5563",
    fontSize: 13,
    margin: 0,
  },
  error: {
    color: "#b42318",
    fontSize: 13,
    margin: 0,
  },
} satisfies Record<string, React.CSSProperties>;
