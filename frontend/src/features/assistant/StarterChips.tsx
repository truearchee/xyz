"use client";

/**
 * Current-lecture chat starters (Stage 8.4 — the renamed "breakdown" chips). STRICTLY about the current
 * lecture; they must NOT imply cross-lecture exam prep (that is 8.6). Clicking a chip pre-fills the
 * composer so the student can edit before sending. Plain buttons, no icons/emoji (App-UI idiom).
 */

const STARTERS = [
  "Explain the key ideas from this lecture simply.",
  "What should I revise first from this lecture?",
  "What are the most assessment-relevant points in this lecture?",
] as const;

export function StarterChips({ scope, onPick }: { scope: string; onPick: (text: string) => void }) {
  return (
    <div aria-label="Suggested questions about this lecture" data-testid={`${scope}-starters`} style={styles.row}>
      {STARTERS.map((text) => (
        <button
          key={text}
          type="button"
          data-testid={`${scope}-starter`}
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
