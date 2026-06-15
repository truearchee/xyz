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

const btnPrimary =
  "min-h-[34px] rounded-full border border-primary bg-primary px-3 text-xs font-medium text-on-primary hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2";
const btnDisabled =
  "min-h-[34px] cursor-not-allowed rounded-full border border-border bg-surface-muted px-3 text-xs font-medium text-text-muted";

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
    <li
      data-testid={`section-asset-row-${asset.id}`}
      className="grid items-start gap-3 rounded-lg border border-border p-3 [grid-template-columns:repeat(auto-fit,minmax(190px,1fr))]"
    >
      <div className="grid min-w-0 gap-1">
        <span className="break-words text-sm font-semibold text-text">{asset.fileName}</span>
        <span className="text-xs text-text-muted">
          {formatBytes(asset.fileSize)} · {asset.mimeType}
        </span>
      </div>
      <span
        data-testid={`section-asset-processing-status-${asset.id}`}
        className="w-fit self-start rounded-full border border-success bg-success-surface px-2.5 py-1 text-xs font-medium capitalize text-success-text"
      >
        {formatProcessingStatus(asset.processingStatus)}
      </span>
      <div data-testid={`section-asset-replace-${asset.id}`} className="grid gap-2">
        <label htmlFor={inputId} className="text-xs font-medium text-text-muted">
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
          className="min-h-[34px] rounded-md border border-border-strong px-[7px] py-[5px] text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2"
          type="file"
        />
        <button
          disabled={disabled || isReplacing || !selectedFile}
          onClick={() => void submitReplace()}
          className={disabled || isReplacing || !selectedFile ? btnDisabled : btnPrimary}
          type="button"
        >
          {isReplacing ? "Replacing..." : "Replace"}
        </button>
        {selectedFile ? (
          <p className="m-0 break-words text-xs text-text-muted">Selected: {selectedFile.name}</p>
        ) : null}
        {errorMessage ? (
          <p
            role="alert"
            className="m-0 rounded-md border border-danger bg-danger-surface px-2 py-1.5 text-xs leading-snug text-danger-text"
          >
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
