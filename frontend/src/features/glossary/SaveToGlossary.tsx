"use client";

import { useCallback, useRef, useState } from "react";

import { api } from "../../lib/api/wrapper";

// Stage 7a: the shared <SaveToGlossary> affordance. It wraps selectable content (a summary in 7a; a
// quiz answer-review surface in 7d) and, when the student has selected text WITHIN that content, offers
// to save it. subjectId is derived server-side from the source (the section's module). The save is
// non-blocking — the entry appears in the glossary in a "generating…" state and the definition fills
// in asynchronously; this component just reports save / duplicate / error.

type SaveState = "idle" | "saving" | "saved" | "duplicate" | "error";
const MAX_TERM = 200;

export function SaveToGlossary({
  moduleSectionId,
  children,
}: {
  moduleSectionId: string;
  children: React.ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState("");
  const [state, setState] = useState<SaveState>("idle");

  const captureSelection = useCallback(() => {
    const selection = typeof window !== "undefined" ? window.getSelection() : null;
    const text = selection ? selection.toString().trim() : "";
    const within =
      !!text &&
      !!containerRef.current &&
      !!selection?.anchorNode &&
      containerRef.current.contains(selection.anchorNode);
    setSelected(within ? text.slice(0, MAX_TERM) : "");
    if (within) {
      setState("idle");
    }
  }, []);

  const onSave = useCallback(async () => {
    if (!selected) return;
    setState("saving");
    try {
      const result = await api.glossary.saveHighlight({
        moduleSectionId,
        term: selected,
        selectedText: selected,
      });
      setState(result.duplicate ? "duplicate" : "saved");
    } catch {
      setState("error");
    }
  }, [moduleSectionId, selected]);

  return (
    <div style={styles.wrap}>
      <div
        ref={containerRef}
        onMouseUp={captureSelection}
        onKeyUp={captureSelection}
        data-testid="save-to-glossary-content"
      >
        {children}
      </div>
      <div style={styles.bar}>
        <button
          type="button"
          data-testid="save-to-glossary"
          disabled={!selected || state === "saving"}
          onClick={onSave}
          style={selected ? styles.primary : styles.disabled}
        >
          {selected
            ? `Save “${truncate(selected)}” to glossary`
            : "Select a term in the text to save it"}
        </button>
        {state === "saved" ? (
          <span data-testid="save-to-glossary-status" data-status="saved" role="status" style={styles.ok}>
            Saved to glossary — generating definition…
          </span>
        ) : null}
        {state === "duplicate" ? (
          <span
            data-testid="save-to-glossary-status"
            data-status="duplicate"
            role="status"
            style={styles.warn}
          >
            Already in your glossary
          </span>
        ) : null}
        {state === "error" ? (
          <span data-testid="save-to-glossary-status" data-status="error" role="alert" style={styles.err}>
            Couldn’t save — try again
          </span>
        ) : null}
      </div>
    </div>
  );
}

function truncate(text: string): string {
  return text.length > 40 ? `${text.slice(0, 40)}…` : text;
}

const styles = {
  wrap: { display: "grid", gap: 8 },
  bar: { alignItems: "center", display: "flex", flexWrap: "wrap", gap: 10 },
  primary: {
    background: "var(--color-primary)",
    border: "1px solid var(--color-primary)",
    borderRadius: 6,
    color: "var(--color-on-primary)",
    cursor: "pointer",
    fontSize: 13,
    fontWeight: 700,
    minHeight: 32,
    padding: "0 14px",
  },
  disabled: {
    background: "var(--color-surface-muted)",
    border: "1px solid var(--color-border)",
    borderRadius: 6,
    color: "var(--color-text-muted)",
    cursor: "default",
    fontSize: 13,
    minHeight: 32,
    padding: "0 14px",
  },
  ok: { color: "var(--color-success-text)", fontSize: 13 },
  warn: { color: "var(--color-warning-text)", fontSize: 13 },
  err: { color: "var(--color-danger-text)", fontSize: 13 },
} satisfies Record<string, React.CSSProperties>;
