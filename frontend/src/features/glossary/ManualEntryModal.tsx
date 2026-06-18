"use client";

import { useEffect, useState } from "react";

import { ManualEntryRequest, type ModuleSummary } from "../../lib/api";
import { api } from "../../lib/api/wrapper";

// Stage 7a manual-add: a term typed directly into the glossary. Per the data model the student MUST
// choose the course (subjectId) — it is the dedup/cache/practice key — and the entry type. The folder
// defaults to "Unsorted" server-side.

const ENTRY_TYPES: { value: ManualEntryRequest.entryType; label: string }[] = [
  { value: ManualEntryRequest.entryType.TERM, label: "Term" },
  { value: ManualEntryRequest.entryType.CONCEPT, label: "Concept" },
  { value: ManualEntryRequest.entryType.FORMULA, label: "Formula" },
];

export function ManualEntryModal({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [modules, setModules] = useState<ModuleSummary[]>([]);
  const [subjectId, setSubjectId] = useState("");
  const [term, setTerm] = useState("");
  const [entryType, setEntryType] = useState<ManualEntryRequest.entryType>(
    ManualEntryRequest.entryType.TERM,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.modules
      .list()
      .then((m) => {
        setModules(m);
        if (m.length > 0) {
          setSubjectId(m[0].id);
        }
      })
      .catch(() => setError("Couldn’t load your courses"));
  }, []);

  async function submit() {
    if (!subjectId || !term.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.glossary.createEntry({ subjectId, term: term.trim(), entryType });
      onSaved();
    } catch {
      setError("Couldn’t save the term — try again");
      setBusy(false);
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label="Add a glossary term" style={styles.overlay}>
      <div data-testid="manual-entry-modal" style={styles.modal}>
        <h2 style={styles.title}>Add a term</h2>

        <label style={styles.label}>
          Course
          <select
            data-testid="manual-entry-course"
            value={subjectId}
            onChange={(e) => setSubjectId(e.target.value)}
            style={styles.input}
          >
            {modules.length === 0 ? <option value="">No courses</option> : null}
            {modules.map((m) => (
              <option key={m.id} value={m.id}>
                {m.title}
              </option>
            ))}
          </select>
        </label>

        <label style={styles.label}>
          Term
          <input
            data-testid="manual-entry-term"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            placeholder="e.g. Mitochondria"
            style={styles.input}
          />
        </label>

        <label style={styles.label}>
          Type
          <select
            data-testid="manual-entry-type"
            value={entryType}
            onChange={(e) => setEntryType(e.target.value as ManualEntryRequest.entryType)}
            style={styles.input}
          >
            {ENTRY_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>

        {error ? (
          <p role="alert" style={styles.error}>
            {error}
          </p>
        ) : null}

        <div style={styles.actions}>
          <button type="button" onClick={onClose} style={styles.secondary}>
            Cancel
          </button>
          <button
            type="button"
            data-testid="manual-entry-save"
            disabled={busy || !subjectId || !term.trim()}
            onClick={submit}
            style={styles.primary}
          >
            {busy ? "Saving…" : "Save term"}
          </button>
        </div>
      </div>
    </div>
  );
}

const styles = {
  overlay: {
    alignItems: "center",
    background: "rgba(17,24,39,0.45)",
    display: "flex",
    inset: 0,
    justifyContent: "center",
    position: "fixed",
    zIndex: 50,
  },
  modal: {
    background: "#ffffff",
    border: "1px solid #d7dde8",
    borderRadius: 10,
    display: "grid",
    gap: 12,
    maxWidth: 420,
    padding: 24,
    width: "90%",
  },
  title: { color: "#111827", fontSize: 18, margin: 0 },
  label: { color: "#374151", display: "grid", fontSize: 13, fontWeight: 700, gap: 4 },
  input: {
    border: "1px solid #d7dde8",
    borderRadius: 6,
    fontSize: 14,
    fontWeight: 400,
    minHeight: 36,
    padding: "0 10px",
  },
  error: { color: "#7f1d1d", fontSize: 13, margin: 0 },
  actions: { display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 4 },
  primary: {
    background: "#174a63",
    border: "1px solid #174a63",
    borderRadius: 6,
    color: "#ffffff",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 700,
    minHeight: 36,
    padding: "0 16px",
  },
  secondary: {
    background: "#ffffff",
    border: "1px solid #d7dde8",
    borderRadius: 6,
    color: "#374151",
    cursor: "pointer",
    fontSize: 13,
    minHeight: 36,
    padding: "0 16px",
  },
} satisfies Record<string, React.CSSProperties>;
