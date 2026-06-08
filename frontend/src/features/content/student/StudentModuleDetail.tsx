"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  type ModuleDetail,
  type SectionListItem,
  type StudentSectionDetail,
} from "../../../lib/api";
import { ForbiddenError, api } from "../../../lib/api/wrapper";
import { StudentSectionView } from "./StudentSectionView";

type StudentModuleDetailProps = {
  moduleId: string;
};

function isStudentSectionDetail(section: unknown): section is StudentSectionDetail {
  return (
    typeof section === "object" &&
    section !== null &&
    "assets" in section &&
    Array.isArray((section as { assets?: unknown }).assets) &&
    "lecturerNotes" in section
  );
}

function errorMessage(caught: unknown): string {
  if (caught instanceof ApiError) {
    const detail = caught.body?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown };
      if (typeof first.msg === "string") {
        return first.msg;
      }
    }
    return caught.message;
  }
  if (caught instanceof Error) {
    return caught.message;
  }
  return "Unexpected error";
}

type SectionRecord = {
  detail: StudentSectionDetail;
  listItem: SectionListItem;
};

export function StudentModuleDetail({ moduleId }: StudentModuleDetailProps) {
  const [module, setModule] = useState<ModuleDetail | null>(null);
  const [sections, setSections] = useState<SectionRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isForbidden, setIsForbidden] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

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
      const sectionDetails = await Promise.all(
        sectionList.map(async (section) => {
          const detail = await api.content.getSection(moduleId, section.id);
          if (!isStudentSectionDetail(detail)) {
            throw new Error("Student section detail was not returned");
          }
          return { detail, listItem: section };
        }),
      );

      setModule(moduleDetail);
      setSections(sectionDetails);
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

  if (isLoading) {
    return (
      <section aria-busy="true" aria-label="Student module detail" style={styles.statePanel}>
        <h1 style={styles.stateTitle}>Loading module content</h1>
      </section>
    );
  }

  if (error) {
    return (
      <section
        aria-label="Student module detail"
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
    <section aria-labelledby="student-module-title" style={styles.shell}>
      <header style={styles.header}>
        <div>
          <p style={styles.eyebrow}>Student module</p>
          <h1 id="student-module-title" style={styles.title}>
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
        <section aria-label="Published sections" style={styles.emptyPanel}>
          <h2 style={styles.stateTitle}>No published sections</h2>
          <p style={styles.stateText}>
            Published content for this module will appear here.
          </p>
        </section>
      ) : (
        <section
          aria-label="Published sections"
          data-testid="student-section-list"
          style={styles.sectionList}
        >
          {sortedSections.map(({ detail }) => (
            <StudentSectionView
              key={detail.id}
              moduleId={moduleId}
              section={detail}
            />
          ))}
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
    overflowWrap: "anywhere",
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
