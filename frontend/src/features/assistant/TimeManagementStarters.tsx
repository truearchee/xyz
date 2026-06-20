"use client";

/**
 * Time-management chat starters (Stage 8.6c). These stay day-level and conversational; saved plans,
 * calendar entries, and exact clock-time blocking are Stage 11.
 */

const STARTERS = [
  "What should I prioritize today?",
  "How should I plan tomorrow around my deadlines?",
  "What should I focus on this weekend?",
] as const;

export function TimeManagementStarters({ scope, onPick }: { scope: string; onPick: (text: string) => void }) {
  return (
    <div aria-label="Time-management starters" data-testid={`${scope}-time-management-starters`} style={styles.row}>
      {STARTERS.map((text) => (
        <button
          key={text}
          type="button"
          data-testid={`${scope}-time-management-starter`}
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
