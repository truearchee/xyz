"use client";

import { useState } from "react";

import type { StudentAssetMeta } from "../../lib/api/models/StudentAssetMeta";
import type { StudentSectionDetail } from "../../lib/api/models/StudentSectionDetail";
import { createAssetDownloadUrl } from "./api/student";

type StudentSectionViewProps = {
  authorization?: string;
  moduleId: string;
  section: StudentSectionDetail | null;
};

export function StudentSectionView({
  authorization,
  moduleId,
  section,
}: StudentSectionViewProps) {
  const [activeAssetId, setActiveAssetId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  if (!section) {
    return (
      <article aria-label="Section detail" style={styles.detail}>
        <h2 style={styles.stateTitle}>No section selected</h2>
      </article>
    );
  }

  async function openAsset(asset: StudentAssetMeta) {
    if (!section) {
      return;
    }
    setActiveAssetId(asset.id);
    setMessage(null);
    try {
      const download = await createAssetDownloadUrl(
        moduleId,
        section.id,
        asset.id,
        authorization,
      );
      const opened = window.open(download.url, "_blank", "noopener,noreferrer");
      if (!opened) {
        setMessage("This file link expired - try opening it again.");
      }
    } catch {
      setMessage("This file link expired - try opening it again.");
    } finally {
      setActiveAssetId(null);
    }
  }

  return (
    <article aria-labelledby="student-section-title" style={styles.detail}>
      <header style={styles.header}>
        <p style={styles.eyebrow}>{section.type}</p>
        <h2 id="student-section-title" style={styles.title}>
          {section.title}
        </h2>
      </header>

      {section.lecturerNotes ? (
        <section aria-label="Lecturer notes" style={styles.notes}>
          {section.lecturerNotes}
        </section>
      ) : null}

      {section.assets.length === 0 ? (
        <p style={styles.empty}>No files available</p>
      ) : (
        <ul aria-label="Section files" style={styles.assetList}>
          {section.assets.map((asset) => (
            <li key={asset.id} style={styles.assetItem}>
              <div style={styles.assetMeta}>
                <span style={styles.assetName}>{asset.fileName}</span>
                <span style={styles.assetDetail}>
                  {asset.mimeType} · {formatBytes(asset.fileSize)}
                </span>
              </div>
              <button
                disabled={activeAssetId === asset.id}
                onClick={() => {
                  void openAsset(asset);
                }}
                style={styles.openButton}
                type="button"
              >
                {activeAssetId === asset.id ? "Opening" : "Open"}
              </button>
            </li>
          ))}
        </ul>
      )}

      {message ? (
        <p aria-live="polite" role="status" style={styles.message}>
          {message}
        </p>
      ) : null}
    </article>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const styles = {
  detail: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    color: "#111827",
    display: "grid",
    gap: 16,
    padding: 20,
  },
  header: {
    display: "grid",
    gap: 4,
  },
  eyebrow: {
    color: "#4b5563",
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: 0,
    margin: 0,
    textTransform: "capitalize",
  },
  title: {
    fontSize: 20,
    lineHeight: 1.3,
    margin: 0,
    overflowWrap: "anywhere",
  },
  notes: {
    background: "#f7faf9",
    border: "1px solid #cfe1da",
    borderRadius: 6,
    color: "#1f2937",
    fontSize: 14,
    lineHeight: 1.5,
    padding: 12,
    whiteSpace: "pre-wrap",
  },
  empty: {
    color: "#4b5563",
    fontSize: 14,
    margin: 0,
  },
  assetList: {
    display: "grid",
    gap: 8,
    listStyle: "none",
    margin: 0,
    padding: 0,
  },
  assetItem: {
    alignItems: "center",
    border: "1px solid #e5e7eb",
    borderRadius: 6,
    display: "flex",
    gap: 12,
    justifyContent: "space-between",
    minHeight: 50,
    padding: "8px 10px",
  },
  assetMeta: {
    display: "grid",
    gap: 2,
    minWidth: 0,
  },
  assetName: {
    fontSize: 14,
    fontWeight: 700,
    overflowWrap: "anywhere",
  },
  assetDetail: {
    color: "#4b5563",
    fontSize: 12,
    overflowWrap: "anywhere",
  },
  openButton: {
    background: "#174a63",
    border: "1px solid #174a63",
    borderRadius: 6,
    color: "#ffffff",
    cursor: "pointer",
    flex: "0 0 auto",
    fontSize: 13,
    fontWeight: 700,
    minHeight: 34,
    padding: "0 12px",
  },
  message: {
    color: "#7f1d1d",
    fontSize: 13,
    margin: 0,
  },
  stateTitle: {
    fontSize: 18,
    lineHeight: 1.35,
    margin: 0,
  },
} satisfies Record<string, React.CSSProperties>;
