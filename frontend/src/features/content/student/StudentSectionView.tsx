import type { StudentSectionDetail } from "../../../lib/api";
import { StudentAssetRow } from "./StudentAssetRow";

type StudentSectionViewProps = {
  moduleId: string;
  section: StudentSectionDetail;
};

function formatSectionType(type: string): string {
  return type.replace(/_/g, " ");
}

function formatDeadline(value: string | null): string {
  if (!value) {
    return "No deadline set";
  }
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function StudentSectionView({
  moduleId,
  section,
}: StudentSectionViewProps) {
  const sectionKey = `${section.orderIndex}-${section.id}`;

  return (
    <article
      data-testid={`student-section-row-${sectionKey}`}
      style={styles.sectionCard}
    >
      <header style={styles.sectionHeader}>
        <p style={styles.sectionMeta}>
          Section {section.orderIndex} · {formatSectionType(section.type)}
        </p>
        <h2 style={styles.sectionTitle}>{section.title}</h2>
      </header>

      <section aria-label={`Lecturer notes for ${section.title}`} style={styles.notesPanel}>
        <h3 style={styles.panelTitle}>Lecturer notes</h3>
        {section.lecturerNotes ? (
          <p style={styles.notes}>{section.lecturerNotes}</p>
        ) : (
          <p style={styles.empty}>No lecturer notes</p>
        )}
      </section>

      {section.type === "lab" ? (
        <section aria-label={`Deadline for ${section.title}`} style={styles.deadlinePanel}>
          <h3 style={styles.panelTitle}>Deadline</h3>
          <p data-testid={`student-section-due-at-${section.id}`} style={styles.notes}>
            {formatDeadline(section.dueAt)}
          </p>
        </section>
      ) : null}

      <section aria-label={`Files for ${section.title}`} style={styles.filesPanel}>
        <h3 style={styles.panelTitle}>Files</h3>
        {section.assets.length === 0 ? (
          <p style={styles.empty}>No files available</p>
        ) : (
          <ul aria-label={`Published files for ${section.title}`} style={styles.assetList}>
            {section.assets.map((asset) => (
              <StudentAssetRow
                asset={asset}
                key={asset.id}
                moduleId={moduleId}
                sectionId={section.id}
              />
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}

const styles = {
  sectionCard: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    display: "grid",
    gap: 14,
    padding: 16,
  },
  sectionHeader: {
    display: "grid",
    gap: 5,
  },
  sectionMeta: {
    color: "#4b5563",
    fontSize: 13,
    fontWeight: 700,
    margin: 0,
    textTransform: "capitalize",
  },
  sectionTitle: {
    color: "#111827",
    fontSize: 18,
    lineHeight: 1.25,
    margin: 0,
    overflowWrap: "anywhere",
  },
  notesPanel: {
    background: "#f7faf9",
    border: "1px solid #cfe1da",
    borderRadius: 6,
    display: "grid",
    gap: 8,
    padding: 12,
  },
  deadlinePanel: {
    background: "#f8fafc",
    border: "1px solid #d7dde8",
    borderRadius: 6,
    display: "grid",
    gap: 8,
    padding: 12,
  },
  filesPanel: {
    display: "grid",
    gap: 8,
  },
  panelTitle: {
    color: "#111827",
    fontSize: 14,
    lineHeight: 1.35,
    margin: 0,
  },
  notes: {
    color: "#1f2937",
    fontSize: 14,
    lineHeight: 1.5,
    margin: 0,
    whiteSpace: "pre-wrap",
  },
  empty: {
    color: "#4b5563",
    fontSize: 14,
    lineHeight: 1.45,
    margin: 0,
  },
  assetList: {
    display: "grid",
    gap: 8,
    listStyle: "none",
    margin: 0,
    padding: 0,
  },
} satisfies Record<string, React.CSSProperties>;
