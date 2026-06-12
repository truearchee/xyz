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
    <div className="grid gap-2.5">
      <label className="grid gap-1.5">
        <span className="text-xs font-bold text-text-muted">Lecturer notes</span>
        <textarea
          aria-label={`Lecturer notes for ${sectionTitle}`}
          disabled={isDisabled}
          onChange={(event) => setDraft(event.currentTarget.value)}
          rows={5}
          className="min-h-[118px] w-full resize-y rounded-md border border-border-strong p-2.5 text-sm text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 disabled:bg-surface-muted disabled:opacity-70"
          value={draft}
        />
      </label>
      <div className="flex flex-wrap items-center gap-2.5">
        <button
          disabled={isDisabled}
          onClick={() => onSave(draft.trim() ? draft : null)}
          className="min-h-[38px] rounded-md border border-primary bg-primary px-3.5 text-sm font-bold text-on-primary hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
          type="button"
        >
          {isSaving ? "Saving notes" : "Save notes"}
        </button>
        <p aria-live="polite" className="m-0 text-xs text-text-muted">
          {initialNotes ? "Persisted notes loaded" : "No notes saved"}
        </p>
      </div>
      {errorMessage ? (
        <p role="alert" className="m-0 text-xs text-danger-text">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}
