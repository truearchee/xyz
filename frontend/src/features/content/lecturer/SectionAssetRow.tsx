"use client";

import { useRef, useState } from "react";

import type { SectionAssetResponse } from "../../../lib/api";

type SectionAssetRowProps = {
  asset: SectionAssetResponse;
  disabled?: boolean;
  errorMessage: string | null;
  isReplacing: boolean;
  onReplace: (assetId: string, file: File) => Promise<void>;
};

export function SectionAssetRow({
  asset,
  disabled = false,
  errorMessage,
  isReplacing,
  onReplace,
}: SectionAssetRowProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const inputId = `section-asset-replace-file-${asset.id}`;

  async function submitReplace() {
    if (!selectedFile) {
      return;
    }

    await onReplace(asset.id, selectedFile);
    setSelectedFile(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  return (
    <li data-testid={`section-asset-row-${asset.id}`} style={styles.row}>
      <div style={styles.meta}>
        <span style={styles.fileName}>{asset.fileName}</span>
        <span style={styles.fileDetail}>
          {formatBytes(asset.fileSize)} · {asset.mimeType}
        </span>
      </div>
      <span
        data-testid={`section-asset-processing-status-${asset.id}`}
        style={styles.processingBadge}
      >
        {formatProcessingStatus(asset.processingStatus)}
      </span>
      <div
        data-testid={`section-asset-replace-${asset.id}`}
        style={styles.replace}
      >
        <label htmlFor={inputId} style={styles.replaceLabel}>
          Replacement PDF
        </label>
        <input
          accept="application/pdf,.pdf"
          disabled={disabled || isReplacing}
          id={inputId}
          onChange={(event) => {
            setSelectedFile(event.currentTarget.files?.[0] ?? null);
          }}
          ref={inputRef}
          style={styles.input}
          type="file"
        />
        <button
          disabled={disabled || isReplacing || !selectedFile}
          onClick={() => void submitReplace()}
          style={
            disabled || isReplacing || !selectedFile
              ? styles.disabledButton
              : styles.button
          }
          type="button"
        >
          {isReplacing ? "Replacing..." : "Replace"}
        </button>
        {selectedFile ? (
          <p style={styles.selected}>Selected: {selectedFile.name}</p>
        ) : null}
        {errorMessage ? (
          <p role="alert" style={styles.error}>
            {errorMessage}
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

function formatProcessingStatus(status: string): string {
  return status.replace(/_/g, " ");
}

const buttonBase = {
  borderRadius: 6,
  fontSize: 13,
  fontWeight: 700,
  minHeight: 34,
  padding: "0 12px",
} satisfies React.CSSProperties;

const styles = {
  row: {
    alignItems: "start",
    border: "1px solid #d7dde8",
    borderRadius: 8,
    display: "grid",
    gap: 12,
    gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
    padding: 12,
  },
  meta: {
    display: "grid",
    gap: 4,
    minWidth: 0,
  },
  fileName: {
    color: "#111827",
    fontSize: 14,
    fontWeight: 700,
    overflowWrap: "anywhere",
  },
  fileDetail: {
    color: "#4b5563",
    fontSize: 12,
  },
  processingBadge: {
    alignSelf: "start",
    background: "#ecfdf5",
    border: "1px solid #a7f3d0",
    borderRadius: 999,
    color: "#047857",
    fontSize: 12,
    fontWeight: 800,
    padding: "4px 9px",
    textTransform: "capitalize",
    width: "fit-content",
  },
  replace: {
    display: "grid",
    gap: 7,
  },
  replaceLabel: {
    color: "#374151",
    fontSize: 12,
    fontWeight: 700,
  },
  input: {
    border: "1px solid #cbd5e1",
    borderRadius: 6,
    fontSize: 13,
    minHeight: 34,
    padding: "5px 7px",
  },
  button: {
    ...buttonBase,
    background: "#174a63",
    border: "1px solid #174a63",
    color: "#ffffff",
    cursor: "pointer",
  },
  disabledButton: {
    ...buttonBase,
    background: "#e5e7eb",
    border: "1px solid #d1d5db",
    color: "#6b7280",
    cursor: "not-allowed",
  },
  selected: {
    color: "#374151",
    fontSize: 12,
    margin: 0,
    overflowWrap: "anywhere",
  },
  error: {
    background: "#fef2f2",
    border: "1px solid #fecaca",
    borderRadius: 6,
    color: "#7f1d1d",
    fontSize: 13,
    lineHeight: 1.4,
    margin: 0,
    padding: "7px 9px",
  },
} satisfies Record<string, React.CSSProperties>;
