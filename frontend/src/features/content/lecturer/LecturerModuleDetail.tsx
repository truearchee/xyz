"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  type ModuleDetail,
  type SectionAssetResponse,
  type SectionDetail,
  type SectionListItem,
  type SectionMetadataPatchRequest,
  type SectionWeekRead,
} from "../../../lib/api";
import {
  replaceSectionAsset,
  uploadSectionAsset,
} from "../../../lib/api/upload";
import { Badge } from "../../../components/ui/Badge";
import { ForbiddenError, api } from "../../../lib/api/wrapper";
import { AssessmentScopePanel } from "../../quiz/AssessmentScopePanel";
import { SectionAssetList } from "./SectionAssetList";
import { SectionMetadataEditor } from "./SectionMetadataEditor";
import { SectionNotesEditor } from "./SectionNotesEditor";
import { SectionPublishControl } from "./SectionPublishControl";
import { SectionTranscriptControl } from "./SectionTranscriptControl";
import { SectionUploadControl } from "./SectionUploadControl";

type LecturerModuleDetailProps = {
  moduleId: string;
};

type SectionRecord = {
  assets: SectionAssetResponse[];
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

function sectionKey(section: SectionDetail, orderIndex: number): string {
  return `${orderIndex}-${slugify(section.title)}-${section.id.slice(0, 8)}`;
}

function slugify(value: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

  return slug || "section";
}

function supportsTranscript(type: string): boolean {
  return type === "lecture" || type === "lab";
}

function errorMessage(caught: unknown): string {
  if (caught instanceof ApiError) {
    return apiErrorMessage(caught);
  }
  if (caught instanceof Error) {
    return caught.message;
  }
  return "Unexpected error";
}

function apiErrorMessage(error: ApiError): string {
  const detail = error.body?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown };
    if (typeof first.msg === "string") {
      return first.msg;
    }
  }
  return error.message;
}

export function LecturerModuleDetail({ moduleId }: LecturerModuleDetailProps) {
  const [module, setModule] = useState<ModuleDetail | null>(null);
  const [sections, setSections] = useState<SectionRecord[]>([]);
  const [weekRows, setWeekRows] = useState<SectionWeekRead[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isForbidden, setIsForbidden] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [savingSectionId, setSavingSectionId] = useState<string | null>(null);
  const [uploadingSectionId, setUploadingSectionId] = useState<string | null>(null);
  const [replacingAssetId, setReplacingAssetId] = useState<string | null>(null);
  const [publishingSectionId, setPublishingSectionId] = useState<string | null>(null);
  const [savingMetadataSectionId, setSavingMetadataSectionId] = useState<string | null>(null);
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});
  const [metadataErrors, setMetadataErrors] = useState<Record<string, string>>({});
  const [uploadErrors, setUploadErrors] = useState<Record<string, string>>({});
  const [replaceErrors, setReplaceErrors] = useState<Record<string, string>>({});
  const [publishErrors, setPublishErrors] = useState<Record<string, string>>({});

  const sortedSections = useMemo(
    () =>
      [...sections].sort(
        (left, right) => left.listItem.orderIndex - right.listItem.orderIndex,
      ),
    [sections],
  );

  const weekRowsById = useMemo(
    () => new Map(weekRows.map((row) => [row.id, row])),
    [weekRows],
  );

  const groupedWeekRows = useMemo(() => {
    const groups = new Map<string, SectionWeekRead[]>();
    for (const row of weekRows) {
      const key = row.weekNumber === null ? "Unstamped" : `Week ${row.weekNumber}`;
      groups.set(key, [...(groups.get(key) ?? []), row]);
    }
    return Array.from(groups.entries());
  }, [weekRows]);

  const loadModule = useCallback(async () => {
    setError(null);
    setIsForbidden(false);

    try {
      const [moduleDetail, sectionList] = await Promise.all([
        api.modules.get(moduleId),
        api.content.listSections(moduleId),
      ]);
      const [details, byWeekRows] = await Promise.all([
        Promise.all(
          sectionList.map(async (section) => {
            const [detail, assetList] = await Promise.all([
              api.content.getSection(moduleId, section.id),
              api.content.listAssets(moduleId, section.id),
            ]);
            if (!isLecturerSectionDetail(detail)) {
              throw new Error("Lecturer section detail was not returned");
            }
            return { assets: assetList.assets, detail, listItem: section };
          }),
        ),
        api.content.listSectionsByWeek(moduleId, null, true),
      ]);

      setModule(moduleDetail);
      setSections(details);
      setWeekRows(byWeekRows);
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

  async function uploadAsset(sectionId: string, file: File, dueAt?: string | null) {
    setUploadingSectionId(sectionId);
    setUploadErrors((current) => {
      const next = { ...current };
      delete next[sectionId];
      return next;
    });

    try {
      await uploadSectionAsset({ dueAt, file, moduleId, sectionId });
      await loadModule();
    } catch (caught) {
      setUploadErrors((current) => ({
        ...current,
        [sectionId]: errorMessage(caught),
      }));
    } finally {
      setUploadingSectionId(null);
    }
  }

  async function saveMetadata(sectionId: string, payload: SectionMetadataPatchRequest) {
    setSavingMetadataSectionId(sectionId);
    setMetadataErrors((current) => {
      const next = { ...current };
      delete next[sectionId];
      return next;
    });

    try {
      await api.content.updateMetadata(moduleId, sectionId, payload);
      await loadModule();
    } catch (caught) {
      setMetadataErrors((current) => ({
        ...current,
        [sectionId]: errorMessage(caught),
      }));
    } finally {
      setSavingMetadataSectionId(null);
    }
  }

  async function replaceAsset(sectionId: string, assetId: string, file: File) {
    setReplacingAssetId(assetId);
    setReplaceErrors((current) => {
      const next = { ...current };
      delete next[assetId];
      return next;
    });

    try {
      await replaceSectionAsset({ assetId, file, moduleId, sectionId });
      await loadModule();
    } catch (caught) {
      setReplaceErrors((current) => ({
        ...current,
        [assetId]: errorMessage(caught),
      }));
    } finally {
      setReplacingAssetId(null);
    }
  }

  async function togglePublishStatus(section: SectionDetail) {
    setPublishingSectionId(section.id);
    setPublishErrors((current) => {
      const next = { ...current };
      delete next[section.id];
      return next;
    });

    try {
      if (section.publishStatus === "published") {
        await api.content.unpublishSection(moduleId, section.id);
      } else {
        await api.content.publishSection(moduleId, section.id);
      }
      await loadModule();
    } catch (caught) {
      setPublishErrors((current) => ({
        ...current,
        [section.id]: errorMessage(caught),
      }));
    } finally {
      setPublishingSectionId(null);
    }
  }

  if (isLoading) {
    return (
      <section aria-busy="true" aria-label="Lecturer module detail" className="rounded-lg border border-border p-6">
        <h1 className="m-0 font-display text-lg leading-snug text-text">Loading module sections</h1>
      </section>
    );
  }

  if (error) {
    return (
      <section
        aria-label="Lecturer module detail"
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
    <section aria-labelledby="lecturer-module-title" className="grid gap-5 [&>*]:min-w-0">
      <header className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="m-0 mb-1.5 text-xs font-medium uppercase text-text-muted">Lecturer module</p>
          <h1 id="lecturer-module-title" className="m-0 break-words font-display text-2xl leading-tight text-text">
            {module?.title ?? "Module"}
          </h1>
        </div>
        {module ? (
          <Badge tone={module.isActive ? "success" : "neutral"}>
            {module.isActive ? "Active" : "Inactive"}
          </Badge>
        ) : null}
      </header>

      <AssessmentScopePanel moduleId={moduleId} />

      {sortedSections.length === 0 ? (
        <section aria-label="Generated sections" className="rounded-lg border border-border p-6">
          <h2 className="m-0 font-display text-lg leading-snug text-text">No generated sections</h2>
        </section>
      ) : (
        <>
          <section
            aria-label="Sections by week"
            data-testid="lecturer-by-week-view"
            className="grid gap-2.5"
          >
            {groupedWeekRows.map(([label, rows]) => (
              <section
                data-testid={`lecturer-week-group-${slugify(label)}`}
                key={label}
                className="grid gap-2.5 rounded-lg border border-border bg-surface-raised p-3.5"
              >
                <h2 className="m-0 font-display text-base leading-snug text-text">{label}</h2>
                <ul className="m-0 grid list-none gap-1.5 p-0">
                  {rows.map((row) => (
                    <li
                      data-testid={`lecturer-by-week-row-${row.id}`}
                      key={row.id}
                      className="grid items-center gap-2.5 text-sm text-text [grid-template-columns:110px_minmax(180px,1fr)_90px_100px]"
                    >
                      <span>{row.sessionDate ?? "No date"}</span>
                      <strong>{row.title}</strong>
                      <span>{formatSectionType(row.type)}</span>
                      <span>{row.publishStatus}</span>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </section>
          <section
            aria-label="Generated sections"
            data-testid="lecturer-section-list"
            className="grid gap-3.5 [&>*]:min-w-0"
          >
            {sortedSections.map(({ assets, detail, listItem }) => {
              const key = sectionKey(detail, listItem.orderIndex);
              const metadata = weekRowsById.get(detail.id);

              return (
                <article
                  data-testid={`lecturer-section-row-${key}`}
                  key={detail.id}
                  className="grid gap-3.5 rounded-lg border border-border bg-surface-raised p-4 [&>*]:min-w-0"
                >
                  <header className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="m-0 mb-1 text-xs font-medium capitalize text-text-muted">
                        Section {listItem.orderIndex} · {formatSectionType(detail.type)}
                      </p>
                      <h2 className="m-0 break-words font-display text-lg leading-snug text-text">{detail.title}</h2>
                    </div>
                    <SectionPublishControl
                      errorMessage={publishErrors[detail.id] ?? null}
                      isSubmitting={publishingSectionId === detail.id}
                      onToggle={() => togglePublishStatus(detail)}
                      publishStatus={detail.publishStatus}
                      sectionKey={key}
                      sectionTitle={detail.title}
                    />
                  </header>
                  <SectionMetadataEditor
                    disabled={
                      savingSectionId === detail.id ||
                      publishingSectionId === detail.id
                    }
                    dueAt={metadata?.dueAt ?? null}
                    errorMessage={metadataErrors[detail.id] ?? null}
                    isSaving={savingMetadataSectionId === detail.id}
                    onSave={(payload) => saveMetadata(detail.id, payload)}
                    sectionTitle={detail.title}
                    sectionType={detail.type}
                    sessionDate={metadata?.sessionDate ?? null}
                    weekNumber={metadata?.weekNumber ?? null}
                  />
                  <SectionNotesEditor
                    errorMessage={saveErrors[detail.id] ?? null}
                    initialNotes={detail.lecturerNotes}
                    isSaving={savingSectionId === detail.id}
                    onSave={(lecturerNotes) => saveNotes(detail.id, lecturerNotes)}
                    sectionTitle={detail.title}
                  />
                  {supportsTranscript(detail.type) ? (
                    <SectionTranscriptControl
                      disabled={
                        savingSectionId === detail.id ||
                        publishingSectionId === detail.id
                      }
                      moduleId={moduleId}
                      sectionId={detail.id}
                      sectionKey={key}
                      sectionTitle={detail.title}
                    />
                  ) : null}
                  <SectionAssetList
                    assets={assets}
                    disabled={
                      uploadingSectionId === detail.id ||
                      savingSectionId === detail.id ||
                      publishingSectionId === detail.id
                    }
                    onReplace={(assetId, file) =>
                      replaceAsset(detail.id, assetId, file)
                    }
                    replaceErrors={replaceErrors}
                    replacingAssetId={replacingAssetId}
                    sectionTitle={detail.title}
                  />
                  <SectionUploadControl
                    disabled={
                      savingSectionId === detail.id ||
                      publishingSectionId === detail.id
                    }
                    errorMessage={uploadErrors[detail.id] ?? null}
                    isUploading={uploadingSectionId === detail.id}
                    onUpload={(file, dueAt) => uploadAsset(detail.id, file, dueAt)}
                    sectionKey={key}
                    sectionTitle={detail.title}
                    sectionType={detail.type}
                  />
                </article>
              );
            })}
          </section>
        </>
      )}
    </section>
  );
}
