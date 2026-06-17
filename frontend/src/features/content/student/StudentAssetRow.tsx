"use client";

import { useState } from "react";

import { ApiError, type StudentAssetMeta } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";

type StudentAssetRowProps = {
  asset: StudentAssetMeta;
  moduleId: string;
  sectionId: string;
};

function errorMessage(caught: unknown): string {
  if (caught instanceof ApiError) {
    const detail = caught.body?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    return caught.message;
  }
  if (caught instanceof Error) {
    return caught.message;
  }
  return "Unable to open file";
}

export function StudentAssetRow({
  asset,
  moduleId,
  sectionId,
}: StudentAssetRowProps) {
  const [error, setError] = useState<string | null>(null);
  const [isOpening, setIsOpening] = useState(false);

  async function openAsset() {
    setError(null);
    setIsOpening(true);

    try {
      if (asset.assetKind === "attachment") {
        const download = await api.content.downloadAttachmentAsset(
          moduleId,
          sectionId,
          asset.id,
          asset.fileName,
        );
        const url = window.URL.createObjectURL(download.blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = download.fileName;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
      } else {
        const download = await api.content.getAssetDownloadUrl(
          moduleId,
          sectionId,
          asset.id,
        );
        window.open(download.url, "_blank", "noopener,noreferrer");
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsOpening(false);
    }
  }

  return (
    <li data-testid={`student-section-asset-row-${asset.id}`} style={styles.row}>
      <div style={styles.assetMeta}>
        <span style={styles.fileName}>{asset.fileName}</span>
        <span style={styles.fileDetail}>
          {asset.mimeType} · {formatBytes(asset.fileSize)}
        </span>
      </div>
      <div style={styles.actions}>
        <button
          aria-label={`Open file ${asset.fileName}`}
          disabled={isOpening}
          onClick={() => {
            void openAsset();
          }}
          style={styles.button}
          type="button"
        >
          {isOpening ? "Opening" : asset.assetKind === "attachment" ? "Download file" : "Open file"}
        </button>
        {error ? (
          <p role="alert" style={styles.error}>
            {error}
          </p>
        ) : null}
      </div>
    </li>
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
  row: {
    alignItems: "center",
    border: "1px solid #e5e7eb",
    borderRadius: 6,
    display: "flex",
    gap: 12,
    justifyContent: "space-between",
    minHeight: 54,
    padding: "10px 12px",
  },
  assetMeta: {
    display: "grid",
    gap: 3,
    minWidth: 0,
  },
  fileName: {
    color: "#111827",
    fontSize: 14,
    fontWeight: 700,
    lineHeight: 1.3,
    overflowWrap: "anywhere",
  },
  fileDetail: {
    color: "#4b5563",
    fontSize: 12,
    lineHeight: 1.35,
    overflowWrap: "anywhere",
  },
  actions: {
    alignItems: "flex-end",
    display: "grid",
    gap: 6,
    justifyItems: "end",
  },
  button: {
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
  error: {
    color: "#7f1d1d",
    fontSize: 13,
    lineHeight: 1.35,
    margin: 0,
    maxWidth: 260,
    textAlign: "right",
  },
} satisfies Record<string, React.CSSProperties>;
