"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  type ModuleDetail,
  type SectionListItem,
  type StudentSectionDetail,
} from "../../../lib/api";
import { Badge } from "../../../components/ui/Badge";
import { ForbiddenError, api } from "../../../lib/api/wrapper";
import { StudentRiskCard } from "../../analytics/StudentRiskCard";
import { StudentWorkloadPlanner } from "../../analytics/StudentWorkloadPlanner";
import { StudentQuizModesPanel } from "../../quiz/StudentQuizModesPanel";
import { StudentSectionView } from "./StudentSectionView";

// Coarse per-section summary flag (§8.1) — one batched call, no per-section fan-out.
const SUMMARY_BADGE: Record<string, { label: string; tone: "neutral" | "info" | "success" } | null> = {
  ready: { label: "Summaries ready", tone: "success" },
  partial: { label: "Summaries partly ready", tone: "info" },
  generating: { label: "Summaries generating", tone: "info" },
  none: { label: "No summary yet", tone: "neutral" },
  not_applicable: null,
};

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
  const [summaryState, setSummaryState] = useState<Map<string, string>>(new Map());
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
      const [moduleDetail, sectionList, summaryList] = await Promise.all([
        api.modules.get(moduleId),
        api.content.listSections(moduleId),
        api.studentSummaries.listSections(moduleId),
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
      setSummaryState(new Map(summaryList.map((item) => [item.id, item.summariesState])));
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
        <div className="min-w-0">
          <p className="m-0 mb-1.5 text-xs font-medium uppercase text-text-muted">Student module</p>
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

      <StudentRiskCard moduleId={moduleId} />

      <StudentWorkloadPlanner moduleId={moduleId} />

      <StudentQuizModesPanel
        moduleId={moduleId}
        sections={sortedSections.map(({ detail }) => detail)}
      />

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
          {sortedSections.map(({ detail }) => {
            const badge = SUMMARY_BADGE[summaryState.get(detail.id) ?? "none"] ?? null;
            return (
              <div key={detail.id} className="grid gap-2">
                <StudentSectionView moduleId={moduleId} section={detail} />
                <div className="flex flex-wrap items-center justify-between gap-3">
                  {badge ? (
                    <Badge tone={badge.tone} className="shrink-0" data-testid={`student-section-summary-flag-${detail.id}`}>
                      {badge.label}
                    </Badge>
                  ) : (
                    <span />
                  )}
                  <Link
                    href={`/student/modules/${moduleId}/sections/${detail.id}`}
                    data-testid={`student-section-open-${detail.id}`}
                    className="rounded-full border border-border bg-surface px-3 py-1.5 text-sm font-medium text-text no-underline hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2"
                  >
                    View summaries →
                  </Link>
                </div>
              </div>
            );
          })}
        </section>
      )}
    </section>
  );
}
