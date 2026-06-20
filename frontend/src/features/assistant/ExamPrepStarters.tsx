"use client";

/**
 * Exam-prep mode chat starters (Stage 8.6b). Pre-fill the composer with exam-review prompts scoped to the
 * selected exam. The assistant discusses the covered weeks, reviews concepts, and highlights the student's
 * weak areas — it never generates a quiz (it points to the Stage 6 practice quiz). Inline idiom.
 */

const STARTERS = [
  "What does this exam cover?",
  "What should I focus on first based on my weak areas?",
  "Explain the key concepts I need to know for this exam.",
] as const;

export function ExamPrepStarters({ scope, onPick }: { scope: string; onPick: (text: string) => void }) {
  return (
    <div aria-label="Exam-prep starters" data-testid={`${scope}-examprep-starters`} style={styles.row}>
      {STARTERS.map((text) => (
        <button
          key={text}
          type="button"
          data-testid={`${scope}-examprep-starter`}
          onClick={() => onPick(text)}
          style={styles.chip}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

const styles = {
  row: { display: "flex", flexWrap: "wrap", gap: 6 },
  chip: {
    background: "#ffffff", border: "1px solid #d7dde8", borderRadius: 9999, color: "#374151",
    cursor: "pointer", fontSize: 12, lineHeight: 1.3, padding: "6px 12px", textAlign: "left",
  },
} satisfies Record<string, React.CSSProperties>;
