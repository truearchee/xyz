import type { SectionListItem } from "../../lib/api/models/SectionListItem";

type StudentSectionListProps = {
  emptyMessage?: string;
  onSelectSection?: (section: SectionListItem) => void;
  sections: SectionListItem[];
  selectedSectionId?: string | null;
};

export function StudentSectionList({
  emptyMessage = "No published sections",
  onSelectSection,
  sections,
  selectedSectionId,
}: StudentSectionListProps) {
  if (sections.length === 0) {
    return <p style={styles.empty}>{emptyMessage}</p>;
  }

  return (
    <ul aria-label="Published sections" style={styles.list}>
      {sections.map((section) => {
        const isSelected = section.id === selectedSectionId;
        return (
          <li key={section.id} style={styles.item}>
            <button
              aria-current={isSelected ? "true" : undefined}
              onClick={() => onSelectSection?.(section)}
              style={{
                ...styles.button,
                ...(isSelected ? styles.selectedButton : {}),
              }}
              type="button"
            >
              <span style={styles.title}>{section.title}</span>
              <span style={styles.meta}>
                {section.type}
                {section.hasAssets ? " · files" : ""}
                {section.hasNotes ? " · notes" : ""}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

const styles = {
  empty: {
    color: "#4b5563",
    fontSize: 14,
    margin: 0,
  },
  list: {
    display: "grid",
    gap: 8,
    listStyle: "none",
    margin: 0,
    padding: 0,
  },
  item: {
    margin: 0,
  },
  button: {
    background: "#ffffff",
    border: "1px solid #d7dde8",
    borderRadius: 6,
    color: "#111827",
    cursor: "pointer",
    display: "grid",
    gap: 4,
    minHeight: 58,
    padding: "10px 12px",
    textAlign: "left",
    width: "100%",
  },
  selectedButton: {
    borderColor: "#174a63",
    boxShadow: "inset 3px 0 0 #174a63",
  },
  title: {
    fontSize: 15,
    fontWeight: 700,
    lineHeight: 1.3,
    overflowWrap: "anywhere",
  },
  meta: {
    color: "#4b5563",
    fontSize: 12,
    lineHeight: 1.35,
    textTransform: "capitalize",
  },
} satisfies Record<string, React.CSSProperties>;
