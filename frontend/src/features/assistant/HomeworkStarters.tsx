"use client";

/**
 * Homework-mode chat starters (Stage 8.6a). These pre-fill the composer with COACHING prompts (the
 * assistant gives hints/questions, never the final answer — enforced server-side by the homework
 * guardrail). Distinct from the lecture StarterChips so homework reads as "bring your problem, get
 * coached". Clicking a chip pre-fills the composer so the student edits before sending. Inline idiom.
 */

const STARTERS = [
  "I'm stuck on a problem — can you give me a hint to get started?",
  "Here's my attempt so far — can you check my approach?",
  "Which concept or method applies to this problem?",
] as const;

export function HomeworkStarters({ scope, onPick }: { scope: string; onPick: (text: string) => void }) {
  return (
    <div aria-label="Homework coaching starters" data-testid={`${scope}-homework-starters`} style={styles.row}>
      {STARTERS.map((text) => (
        <button
          key={text}
          type="button"
          data-testid={`${scope}-homework-starter`}
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
