"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, type TranscriptMeta } from "../../../lib/api";
import { uploadTranscript } from "../../../lib/api/upload";
import { api } from "../../../lib/api/wrapper";
import { TranscriptStatusBadge } from "./TranscriptStatusBadge";
import { TranscriptSummaryPanel } from "./TranscriptSummaryPanel";

type SectionTranscriptControlProps = {
  disabled?: boolean;
  moduleId: string;
  sectionId: string;
  sectionKey: string;
  sectionTitle: string;
};

const ACCEPTED_EXTENSIONS = [".vtt", ".txt"];

export function SectionTranscriptControl({
  disabled = false,
  moduleId,
  sectionId,
  sectionKey,
  sectionTitle,
}: SectionTranscriptControlProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [transcript, setTranscript] = useState<TranscriptMeta | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingReplace, setConfirmingReplace] = useState(false);
  const [hasPendingReplacement, setHasPendingReplacement] = useState(false);

  const fileInputId = `section-transcript-file-${sectionKey}`;

  const loadActiveTranscript = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const activeTranscript = await api.transcripts.getActive(
        moduleId,
        sectionId,
      );
      setTranscript(activeTranscript);
    } catch (caught) {
      if (isTranscriptNotFound(caught)) {
        setTranscript(null);
      } else {
        setError(errorMessage(caught));
      }
    } finally {
      setIsLoading(false);
    }
  }, [moduleId, sectionId]);

  useEffect(() => {
    void loadActiveTranscript();
  }, [loadActiveTranscript]);

  // Poll the active-summary preview while a transcript exists: surfaces whether a replacement is
  // processing ("new version processing" badge) and detects the atomic swap (the active id flips →
  // refresh to the new active). The active summaries themselves stay on the summary panel.
  const activeTranscriptId = transcript?.id ?? null;
  useEffect(() => {
    if (activeTranscriptId === null) {
      setHasPendingReplacement(false);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const preview = await api.transcripts.getActiveSummaryPreview(
          moduleId,
          sectionId,
        );
        if (cancelled) return;
        setHasPendingReplacement(preview.hasPendingReplacement);
        if (preview.activeTranscriptId !== activeTranscriptId) {
          void loadActiveTranscript(); // a replacement swapped in → show the new active
        }
      } catch {
        // transient / transcript missing — keep the last known state
      }
    };
    void poll();
    const intervalId = window.setInterval(() => void poll(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [activeTranscriptId, loadActiveTranscript, moduleId, sectionId]);

  function selectFile(file: File | null) {
    setError(null);

    if (!file) {
      setSelectedFile(null);
      return;
    }

    if (!hasAcceptedExtension(file.name)) {
      setSelectedFile(null);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
      setError("Transcript upload accepts .vtt or .txt files.");
      return;
    }

    setSelectedFile(file);
  }

  async function submitUpload() {
    if (!selectedFile) {
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const uploadedTranscript = await uploadTranscript({
        file: selectedFile,
        moduleId,
        sectionId,
      });
      if (uploadedTranscript.lifecycleState === "pending") {
        // A replacement is processing alongside the still-active transcript — keep showing the
        // active; the preview poll flips the "new version processing" badge and the swap.
        setHasPendingReplacement(true);
        await loadActiveTranscript();
      } else {
        setTranscript(uploadedTranscript);
      }
      setSelectedFile(null);
      setConfirmingReplace(false);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <section
      aria-label={`Transcript upload for ${sectionTitle}`}
      data-testid={`section-transcript-control-${sectionKey}`}
      className="grid gap-2.5 border-t border-border pt-3.5"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="m-0 font-display text-base leading-snug text-text">Transcript</h3>
        </div>
        {isLoading ? <span className="shrink-0 text-xs font-bold text-text-muted">Loading status</span> : null}
      </div>

      {transcript ? (
        <div className="grid gap-1.5">
          <span className="break-words text-sm font-bold text-text">{transcript.originalFileName}</span>
          <span className="break-words text-xs text-text-muted">
            {transcript.mimeType} · {formatBytes(transcript.fileSize)}
          </span>
          <TranscriptStatusBadge
            moduleId={moduleId}
            onTranscriptMissing={() => setTranscript(null)}
            sectionId={sectionId}
            sectionKey={sectionKey}
            transcript={transcript}
          />
          {hasPendingReplacement ? (
            <p
              data-testid={`section-transcript-pending-${sectionKey}`}
              role="status"
              className="m-0 rounded-md border border-info bg-info-surface px-2.5 py-2 text-xs font-bold text-info-text"
            >
              New version processing… the current summaries stay until it completes.
            </p>
          ) : null}
          <TranscriptSummaryPanel
            moduleId={moduleId}
            sectionId={sectionId}
            sectionKey={sectionKey}
            transcriptId={transcript.id}
          />
          <div
            data-testid={`section-transcript-replace-control-${sectionKey}`}
            className={fieldsClass}
          >
            <label htmlFor={fileInputId} className={labelClass}>
              Replace transcript for {sectionTitle}
            </label>
            <input
              accept=".vtt,.txt"
              data-testid={`section-transcript-replace-upload-${sectionKey}`}
              disabled={disabled || isUploading}
              id={fileInputId}
              onChange={(event) => {
                setConfirmingReplace(false);
                selectFile(event.currentTarget.files?.[0] ?? null);
              }}
              ref={inputRef}
              className={inputClass}
              type="file"
            />
            {confirmingReplace ? (
              <div className="grid gap-2 [grid-column:1/-1]">
                <p role="status" className="m-0 text-xs leading-snug text-text-muted">
                  {hasPendingReplacement
                    ? "A replacement is already processing. Uploading a new one will discard the pending version and restart processing."
                    : "Replacing supersedes the current transcript and regenerates its summaries."}
                </p>
                <div className="flex gap-2">
                  <button
                    data-testid={`section-transcript-replace-confirm-${sectionKey}`}
                    disabled={isUploading}
                    onClick={() => void submitUpload()}
                    className={isUploading ? btnDisabled : btnPrimary}
                    type="button"
                  >
                    {isUploading ? "Replacing..." : "Confirm replace"}
                  </button>
                  <button
                    disabled={isUploading}
                    onClick={() => setConfirmingReplace(false)}
                    className={btnSecondary}
                    type="button"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                data-testid={`section-transcript-replace-${sectionKey}`}
                disabled={disabled || isUploading || !selectedFile}
                onClick={() => setConfirmingReplace(true)}
                className={disabled || isUploading || !selectedFile ? btnDisabled : btnPrimary}
                type="button"
              >
                Replace transcript
              </button>
            )}
            {selectedFile ? (
              <p className="m-0 break-words text-xs text-text-muted">Selected: {selectedFile.name}</p>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="grid gap-2">
          <p
            data-testid={`section-transcript-status-${sectionKey}`}
            role="status"
            className="m-0 text-sm text-text-muted"
          >
            No transcript uploaded yet.
          </p>
          <div className={fieldsClass}>
            <label htmlFor={fileInputId} className={labelClass}>
              Transcript file for {sectionTitle}
            </label>
            <input
              accept=".vtt,.txt"
              data-testid={`section-transcript-upload-${sectionKey}`}
              disabled={disabled || isLoading || isUploading}
              id={fileInputId}
              onChange={(event) => {
                selectFile(event.currentTarget.files?.[0] ?? null);
              }}
              ref={inputRef}
              className={inputClass}
              type="file"
            />
            <button
              disabled={disabled || isLoading || isUploading || !selectedFile}
              onClick={() => void submitUpload()}
              className={
                disabled || isLoading || isUploading || !selectedFile ? btnDisabled : btnPrimary
              }
              type="button"
            >
              {isUploading ? "Uploading..." : "Upload transcript"}
            </button>
          </div>
          {selectedFile ? (
            <p className="m-0 break-words text-xs text-text-muted">Selected: {selectedFile.name}</p>
          ) : null}
        </div>
      )}

      {error ? (
        <p
          data-testid={`section-transcript-error-${sectionKey}`}
          role="alert"
          className="m-0 rounded-md border border-danger bg-danger-surface px-2.5 py-2 text-sm leading-snug text-danger-text"
        >
          {error}
        </p>
      ) : null}
    </section>
  );
}

// Token class constants (semantic tokens only). Buttons stay raw <button> to preserve their exact
// data-testids/names/disabled logic byte-for-byte (lower risk than threading data-testid through Button).
const fieldsClass = "grid items-end gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(180px,1fr))]";
const labelClass = "text-xs font-bold text-text-muted [grid-column:1/-1]";
const inputClass =
  "min-h-[38px] rounded-md border border-border-strong px-2.5 py-[7px] text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2";
const btnPrimary =
  "min-h-[38px] rounded-md border border-primary bg-primary px-3.5 text-sm font-bold text-on-primary hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2";
const btnDisabled =
  "min-h-[38px] cursor-not-allowed rounded-md border border-border bg-surface-muted px-3.5 text-sm font-bold text-text-muted";
const btnSecondary =
  "min-h-[38px] rounded-md border border-border-strong bg-surface px-3.5 text-sm font-bold text-text hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2";

function hasAcceptedExtension(fileName: string): boolean {
  const lowerName = fileName.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((extension) => lowerName.endsWith(extension));
}

function detailCode(caught: unknown): string | null {
  if (caught instanceof ApiError && typeof caught.body?.detail === "string") {
    return caught.body.detail;
  }
  return null;
}

function isTranscriptNotFound(caught: unknown): boolean {
  return (
    caught instanceof ApiError &&
    caught.status === 404 &&
    detailCode(caught) === "TRANSCRIPT_NOT_FOUND"
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

function formatBytes(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

