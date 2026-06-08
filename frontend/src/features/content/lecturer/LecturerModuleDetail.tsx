"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  type ModuleDetail,
  type SectionAssetResponse,
  type SectionDetail,
  type SectionListItem,
} from "../../../lib/api";
import {
  replaceSectionAsset,
  uploadSectionAsset,
} from "../../../lib/api/upload";
import { ForbiddenError, api } from "../../../lib/api/wrapper";
import { SectionAssetList } from "./SectionAssetList";
import { SectionNotesEditor } from "./SectionNotesEditor";
import { SectionPublishControl } from "./SectionPublishControl";
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
  const [error, setError] = useState<string | null>(null);
  const [isForbidden, setIsForbidden] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [savingSectionId, setSavingSectionId] = useState<string | null>(null);
  const [uploadingSectionId, setUploadingSectionId] = useState<string | null>(null);
  const [replacingAssetId, setReplacingAssetId] = useState<string | null>(null);
  const [publishingSectionId, setPublishingSectionId] = useState<string | null>(null);
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});
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
          const [detail, assetList] = await Promise.all([
            api.content.getSection(moduleId, section.id),
            api.content.listAssets(moduleId, section.id),
          ]);
          if (!isLecturerSectionDetail(detail)) {
            throw new Error("Lecturer section detail was not returned");
          }
          return { assets: assetList.assets, detail, listItem: section };
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

  async function uploadAsset(sectionId: string, file: File) {
    setUploadingSectionId(sectionId);
    setUploadErrors((current) => {
      const next = { ...current };
      delete next[sectionId];
      return next;
    });

    try {
      await uploadSectionAsset({ file, moduleId, sectionId });
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
          {sortedSections.map(({ assets, detail, listItem }) => {
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
                  <SectionPublishControl
                    errorMessage={publishErrors[detail.id] ?? null}
                    isSubmitting={publishingSectionId === detail.id}
                    onToggle={() => togglePublishStatus(detail)}
                    publishStatus={detail.publishStatus}
                    sectionKey={sectionKey}
                    sectionTitle={detail.title}
                  />
                </header>
                <SectionNotesEditor
                  errorMessage={saveErrors[detail.id] ?? null}
                  initialNotes={detail.lecturerNotes}
                  isSaving={savingSectionId === detail.id}
                  onSave={(lecturerNotes) => saveNotes(detail.id, lecturerNotes)}
                  sectionTitle={detail.title}
                />
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
                  onUpload={(file) => uploadAsset(detail.id, file)}
                  sectionKey={sectionKey}
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
