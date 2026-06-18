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

      <AssessmentScopePanel moduleId={moduleId} />

      {sortedSections.length === 0 ? (
        <section aria-label="Generated sections" style={styles.emptyPanel}>
          <h2 style={styles.stateTitle}>No generated sections</h2>
        </section>
      ) : (
        <>
          <section
            aria-label="Sections by week"
            data-testid="lecturer-by-week-view"
            style={styles.weekList}
          >
            {groupedWeekRows.map(([label, rows]) => (
              <section
                data-testid={`lecturer-week-group-${slugify(label)}`}
                key={label}
                style={styles.weekGroup}
              >
                <h2 style={styles.weekTitle}>{label}</h2>
                <ul style={styles.weekRows}>
                  {rows.map((row) => (
                    <li data-testid={`lecturer-by-week-row-${row.id}`} key={row.id} style={styles.weekRow}>
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
            style={styles.sectionList}
          >
            {sortedSections.map(({ assets, detail, listItem }) => {
              const key = sectionKey(detail, listItem.orderIndex);
              const metadata = weekRowsById.get(detail.id);

              return (
                <article
                  data-testid={`lecturer-section-row-${key}`}
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
  weekGroup: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    display: "grid",
    gap: 10,
    padding: 14,
  },
  weekList: {
    display: "grid",
    gap: 10,
  },
  weekRow: {
    alignItems: "center",
    display: "grid",
    gap: 10,
    gridTemplateColumns: "110px minmax(180px, 1fr) 90px 100px",
  },
  weekRows: {
    display: "grid",
    gap: 6,
    listStyle: "none",
    margin: 0,
    padding: 0,
  },
  weekTitle: {
    color: "#111827",
    fontSize: 16,
    lineHeight: 1.3,
    margin: 0,
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
