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
      const download = await api.content.getAssetDownloadUrl(
        moduleId,
        sectionId,
        asset.id,
      );
      window.open(download.url, "_blank", "noopener,noreferrer");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsOpening(false);
    }
  }

  return (
    <li
      data-testid={`student-section-asset-row-${asset.id}`}
      className="flex min-h-[54px] items-center justify-between gap-3 rounded-md border border-border px-3 py-2.5"
    >
      <div className="grid min-w-0 gap-0.5">
        <span className="break-words text-sm font-semibold leading-snug text-text">{asset.fileName}</span>
        <span className="break-words text-xs leading-snug text-text-muted">
          {asset.mimeType} · {formatBytes(asset.fileSize)}
        </span>
      </div>
      <div className="grid justify-items-end gap-1.5">
        <button
          aria-label={`Open file ${asset.fileName}`}
          disabled={isOpening}
          onClick={() => {
            void openAsset();
          }}
          className="min-h-[34px] shrink-0 rounded-full border border-primary bg-primary px-3 text-xs font-medium text-on-primary hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
          type="button"
        >
          {isOpening ? "Opening" : "Open file"}
        </button>
        {error ? (
          <p role="alert" className="m-0 max-w-[260px] text-right text-xs leading-snug text-danger-text">
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
