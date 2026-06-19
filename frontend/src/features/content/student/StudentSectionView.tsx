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
      className="grid gap-3.5 rounded-lg border border-border bg-surface-raised p-4"
    >
      <header className="grid gap-1">
        <p className="m-0 text-xs font-medium capitalize text-text-muted">
          Section {section.orderIndex} · {formatSectionType(section.type)}
        </p>
        <h2 className="m-0 break-words font-display text-lg leading-snug text-text">{section.title}</h2>
      </header>

      <section
        aria-label={`Lecturer notes for ${section.title}`}
        className="grid gap-2 rounded-md border border-border bg-surface-muted p-3"
      >
        <h3 className="m-0 text-sm leading-snug text-text">Lecturer notes</h3>
        {section.lecturerNotes ? (
          <p className="m-0 whitespace-pre-wrap text-sm leading-normal text-text">{section.lecturerNotes}</p>
        ) : (
          <p className="m-0 text-sm leading-snug text-text-muted">No lecturer notes</p>
        )}
      </section>

      {section.type === "lab" ? (
        <section
          aria-label={`Deadline for ${section.title}`}
          className="grid gap-2 rounded-md border border-border bg-surface-muted p-3"
        >
          <h3 className="m-0 text-sm leading-snug text-text">Deadline</h3>
          <p data-testid={`student-section-due-at-${section.id}`} className="m-0 text-sm leading-normal text-text">
            {formatDeadline(section.dueAt)}
          </p>
        </section>
      ) : null}

      <section aria-label={`Files for ${section.title}`} className="grid gap-2">
        <h3 className="m-0 text-sm leading-snug text-text">Files</h3>
        {section.assets.length === 0 ? (
          <p className="m-0 text-sm leading-snug text-text-muted">No files available</p>
        ) : (
          <ul aria-label={`Published files for ${section.title}`} className="m-0 grid list-none gap-2 p-0">
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
