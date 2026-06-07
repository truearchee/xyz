"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { ModuleDetail, SectionDetail, SectionListItem } from "../../../lib/api";
import { ForbiddenError, api } from "../../../lib/api/wrapper";
import { SectionNotesEditor } from "./SectionNotesEditor";

type LecturerModuleDetailProps = {
  moduleId: string;
};

type SectionRecord = {
  detail: SectionDetail;
  listItem: SectionListItem;
};

function isLecturerSectionDetail(section: unknown): section is SectionDetail {
  return (
    typeof section === "object" &&
    section !== null &&
    "publishStatus" in section &&
    "lecturerNotes" in section
  );
}

function formatSectionType(type: string): string {
  return type.replace(/_/g, " ");
}

function formatPublishStatus(status: string): string {
  if (status === "published") {
    return "Published";
  }
  if (status === "unpublished") {
    return "Unpublished";
  }
  return "Draft";
}

function errorMessage(caught: unknown): string {
  if (caught instanceof Error) {
    return caught.message;
  }
  return "Unexpected error";
}

export function LecturerModuleDetail({ moduleId }: LecturerModuleDetailProps) {
  const [module, setModule] = useState<ModuleDetail | null>(null);
  const [sections, setSections] = useState<SectionRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isForbidden, setIsForbidden] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [savingSectionId, setSavingSectionId] = useState<string | null>(null);
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});

  const sortedSections = useMemo(
    () =>
      [...sections].sort(
        (left, right) => left.listItem.orderIndex - right.listItem.orderIndex,
      ),
    [sections],
  );

  const loadModule = useCallback(async () => {
    setError(null);
    setIsForbidden(false);

    try {
      const [moduleDetail, sectionList] = await Promise.all([
        api.modules.get(moduleId),
        api.content.listSections(moduleId),
      ]);
      const details = await Promise.all(
        sectionList.map(async (section) => {
          const detail = await api.content.getSection(moduleId, section.id);
          if (!isLecturerSectionDetail(detail)) {
            throw new Error("Lecturer section detail was not returned");
          }
          return { detail, listItem: section };
        }),
      );

      setModule(moduleDetail);
      setSections(details);
    } catch (caught) {
      if (caught instanceof ForbiddenError) {
        setIsForbidden(true);
        setError("You are not allowed to open this module.");
      } else {
        setError(errorMessage(caught));
      }
    } finally {
      setIsLoading(false);
    }
  }, [moduleId]);

  useEffect(() => {
    setIsLoading(true);
    void loadModule();
  }, [loadModule]);

  async function saveNotes(sectionId: string, lecturerNotes: string | null) {
    setSavingSectionId(sectionId);
    setSaveErrors((current) => {
      const next = { ...current };
      delete next[sectionId];
      return next;
    });

    try {
      await api.content.updateNotes(moduleId, sectionId, { lecturerNotes });
      await loadModule();
    } catch (caught) {
      setSaveErrors((current) => ({
        ...current,
        [sectionId]: errorMessage(caught),
      }));
    } finally {
      setSavingSectionId(null);
    }
  }

  if (isLoading) {
    return (
      <section aria-busy="true" aria-label="Lecturer module detail" style={styles.statePanel}>
        <h1 style={styles.stateTitle}>Loading module sections</h1>
      </section>
    );
  }

  if (error) {
    return (
      <section
        aria-label="Lecturer module detail"
        role={isForbidden ? undefined : "alert"}
        style={isForbidden ? styles.forbiddenPanel : styles.errorPanel}
      >
        <h1 style={styles.stateTitle}>
          {isForbidden ? "Unauthorized module" : "Unable to load module"}
        </h1>
        <p style={styles.stateText}>{error}</p>
      </section>
    );
  }

  return (
    <section aria-labelledby="lecturer-module-title" style={styles.shell}>
      <header style={styles.header}>
        <div>
          <p style={styles.eyebrow}>Lecturer module</p>
          <h1 id="lecturer-module-title" style={styles.title}>
            {module?.title ?? "Module"}
          </h1>
        </div>
        {module ? (
          <span style={module.isActive ? styles.activeBadge : styles.inactiveBadge}>
            {module.isActive ? "Active" : "Inactive"}
          </span>
        ) : null}
      </header>

      {sortedSections.length === 0 ? (
        <section aria-label="Generated sections" style={styles.emptyPanel}>
          <h2 style={styles.stateTitle}>No generated sections</h2>
        </section>
      ) : (
        <section
          aria-label="Generated sections"
          data-testid="lecturer-section-list"
          style={styles.sectionList}
        >
          {sortedSections.map(({ detail, listItem }) => {
            const sectionKey = `${listItem.orderIndex}-${detail.id}`;

            return (
              <article
                data-testid={`lecturer-section-row-${sectionKey}`}
                key={detail.id}
                style={styles.sectionCard}
              >
                <header style={styles.sectionHeader}>
                  <div>
                    <p style={styles.sectionMeta}>
                      Section {listItem.orderIndex} · {formatSectionType(detail.type)}
                    </p>
                    <h2 style={styles.sectionTitle}>{detail.title}</h2>
                  </div>
                  <span
                    data-testid={`section-publish-status-${sectionKey}`}
                    style={styles.statusBadge}
                  >
                    {formatPublishStatus(detail.publishStatus)}
                  </span>
                </header>
                <SectionNotesEditor
                  errorMessage={saveErrors[detail.id] ?? null}
                  initialNotes={detail.lecturerNotes}
                  isSaving={savingSectionId === detail.id}
                  onSave={(lecturerNotes) => saveNotes(detail.id, lecturerNotes)}
                  sectionTitle={detail.title}
                />
              </article>
            );
          })}
        </section>
      )}
    </section>
  );
}

const badgeBase = {
  borderRadius: 999,
  flex: "0 0 auto",
  fontSize: 13,
  fontWeight: 700,
  padding: "4px 10px",
} satisfies React.CSSProperties;

const styles = {
  shell: {
    display: "grid",
    gap: 18,
  },
  header: {
    alignItems: "flex-start",
    display: "flex",
    gap: 16,
    justifyContent: "space-between",
  },
  eyebrow: {
    color: "#4b5563",
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: 0,
    margin: "0 0 6px",
    textTransform: "uppercase",
  },
  title: {
    color: "#111827",
    fontSize: 26,
    lineHeight: 1.2,
    margin: 0,
  },
  activeBadge: {
    ...badgeBase,
    background: "#e8f5e9",
    border: "1px solid #a7d8ad",
    color: "#1f6f35",
  },
  inactiveBadge: {
    ...badgeBase,
    background: "#f3f4f6",
    border: "1px solid #d1d5db",
    color: "#4b5563",
  },
  sectionList: {
    display: "grid",
    gap: 14,
  },
  sectionCard: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    display: "grid",
    gap: 14,
    padding: 16,
  },
  sectionHeader: {
    alignItems: "flex-start",
    display: "flex",
    gap: 12,
    justifyContent: "space-between",
  },
  sectionMeta: {
    color: "#4b5563",
    fontSize: 13,
    fontWeight: 700,
    margin: "0 0 5px",
    textTransform: "capitalize",
  },
  sectionTitle: {
    color: "#111827",
    fontSize: 18,
    lineHeight: 1.25,
    margin: 0,
  },
  statusBadge: {
    ...badgeBase,
    background: "#eef2ff",
    border: "1px solid #c7d2fe",
    color: "#3730a3",
  },
  emptyPanel: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    padding: 24,
  },
  statePanel: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    padding: 24,
  },
  errorPanel: {
    border: "1px solid #f0b4b4",
    borderRadius: 8,
    color: "#7f1d1d",
    padding: 24,
  },
  forbiddenPanel: {
    border: "1px solid #fed7aa",
    borderRadius: 8,
    color: "#7c2d12",
    padding: 24,
  },
  stateTitle: {
    fontSize: 18,
    lineHeight: 1.35,
    margin: 0,
  },
  stateText: {
    fontSize: 14,
    lineHeight: 1.5,
    margin: "8px 0 0",
  },
} satisfies Record<string, React.CSSProperties>;
