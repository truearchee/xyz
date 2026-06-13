"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  type ModuleDetail,
  type SectionListItem,
  type StudentSectionDetail,
} from "../../../lib/api";
import { ForbiddenError, api } from "../../../lib/api/wrapper";
import { Badge } from "../../../components/ui/Badge";
import { StudentSectionView } from "./StudentSectionView";

// Post-4.9 Workstream B: the per-section summary BADGE + the "View summaries →" hop are gone — each section
// block now renders the brief + detailed summaries inline (via StudentSectionView → SectionSummaries), so the
// student reads everything in one block on this page. The coarse `studentSummaries.listSections` flag call is
// therefore no longer fetched here (the inline block's own §4.3 state is the signal).

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
      <section aria-busy="true" aria-label="Student module detail" className="rounded-lg border border-border p-6">
        <h1 className="m-0 font-display text-lg leading-snug text-text">Loading module content</h1>
      </section>
    );
  }

  if (error) {
    return (
      <section
        aria-label="Student module detail"
        role={isForbidden ? undefined : "alert"}
        className={
          isForbidden
            ? "rounded-lg border border-warning p-6 text-warning-text"
            : "rounded-lg border border-danger p-6 text-danger-text"
        }
      >
        <h1 className="m-0 font-display text-lg leading-snug">
          {isForbidden ? "Unauthorized module" : "Unable to load module"}
        </h1>
        <p className="mt-2 text-sm leading-normal">{error}</p>
      </section>
    );
  }

  return (
    <section aria-labelledby="student-module-title" className="grid gap-5">
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="m-0 mb-1.5 text-xs font-bold uppercase text-text-muted">Student module</p>
          <h1 id="student-module-title" className="m-0 break-words font-display text-2xl leading-tight text-text">
            {module?.title ?? "Module"}
          </h1>
        </div>
        {module ? (
          <Badge tone={module.isActive ? "success" : "neutral"}>
            {module.isActive ? "Active" : "Inactive"}
          </Badge>
        ) : null}
      </header>

      {sortedSections.length === 0 ? (
        <section aria-label="Published sections" className="rounded-lg border border-border p-6">
          <h2 className="m-0 font-display text-lg leading-snug text-text">No published sections</h2>
          <p className="mt-2 text-sm leading-normal text-text-muted">
            Published content for this module will appear here.
          </p>
        </section>
      ) : (
        <section
          aria-label="Published sections"
          data-testid="student-section-list"
          className="grid gap-3.5"
        >
          {sortedSections.map(({ detail }) => (
            <StudentSectionView key={detail.id} moduleId={moduleId} section={detail} />
          ))}
        </section>
      )}
    </section>
  );
}

