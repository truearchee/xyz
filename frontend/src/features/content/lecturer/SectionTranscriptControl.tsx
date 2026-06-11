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
      style={styles.shell}
    >
      <div style={styles.header}>
        <div>
          <h3 style={styles.title}>Transcript</h3>
        </div>
        {isLoading ? <span style={styles.meta}>Loading status</span> : null}
      </div>

      {transcript ? (
        <div style={styles.current}>
          <span style={styles.fileName}>{transcript.originalFileName}</span>
          <span style={styles.fileDetail}>
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
              style={styles.pending}
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
            style={styles.fields}
          >
            <label htmlFor={fileInputId} style={styles.label}>
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
              style={styles.input}
              type="file"
            />
            {confirmingReplace ? (
              <div style={styles.confirm}>
                <p role="status" style={styles.confirmText}>
                  {hasPendingReplacement
                    ? "A replacement is already processing. Uploading a new one will discard the pending version and restart processing."
                    : "Replacing supersedes the current transcript and regenerates its summaries."}
                </p>
                <div style={styles.confirmActions}>
                  <button
                    data-testid={`section-transcript-replace-confirm-${sectionKey}`}
                    disabled={isUploading}
                    onClick={() => void submitUpload()}
                    style={isUploading ? styles.disabledButton : styles.button}
                    type="button"
                  >
                    {isUploading ? "Replacing..." : "Confirm replace"}
                  </button>
                  <button
                    disabled={isUploading}
                    onClick={() => setConfirmingReplace(false)}
                    style={styles.secondaryButton}
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
                style={
                  disabled || isUploading || !selectedFile
                    ? styles.disabledButton
                    : styles.button
                }
                type="button"
              >
                Replace transcript
              </button>
            )}
            {selectedFile ? (
              <p style={styles.selected}>Selected: {selectedFile.name}</p>
            ) : null}
          </div>
        </div>
      ) : (
        <div style={styles.empty}>
          <p
            data-testid={`section-transcript-status-${sectionKey}`}
            role="status"
            style={styles.emptyText}
          >
            No transcript uploaded yet.
          </p>
          <div style={styles.fields}>
            <label htmlFor={fileInputId} style={styles.label}>
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
              style={styles.input}
              type="file"
            />
            <button
              disabled={disabled || isLoading || isUploading || !selectedFile}
              onClick={() => void submitUpload()}
              style={
                disabled || isLoading || isUploading || !selectedFile
                  ? styles.disabledButton
                  : styles.button
              }
              type="button"
            >
              {isUploading ? "Uploading..." : "Upload transcript"}
            </button>
          </div>
          {selectedFile ? (
            <p style={styles.selected}>Selected: {selectedFile.name}</p>
          ) : null}
        </div>
      )}

      {error ? (
        <p
          data-testid={`section-transcript-error-${sectionKey}`}
          role="alert"
          style={styles.error}
        >
          {error}
        </p>
      ) : null}
    </section>
  );
}

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

const buttonBase = {
  borderRadius: 6,
  fontSize: 14,
  fontWeight: 700,
  minHeight: 38,
  padding: "0 14px",
} satisfies React.CSSProperties;

const styles = {
  shell: {
    borderTop: "1px solid #e5e7eb",
    display: "grid",
    gap: 10,
    paddingTop: 14,
  },
  header: {
    alignItems: "flex-start",
    display: "flex",
    gap: 12,
    justifyContent: "space-between",
  },
  title: {
    color: "#111827",
    fontSize: 16,
    lineHeight: 1.3,
    margin: 0,
  },
  meta: {
    color: "#4b5563",
    flex: "0 0 auto",
    fontSize: 13,
    fontWeight: 700,
  },
  current: {
    display: "grid",
    gap: 6,
  },
  fileName: {
    color: "#111827",
    fontSize: 14,
    fontWeight: 700,
    overflowWrap: "anywhere",
  },
  fileDetail: {
    color: "#4b5563",
    fontSize: 13,
    overflowWrap: "anywhere",
  },
  empty: {
    display: "grid",
    gap: 8,
  },
  emptyText: {
    color: "#4b5563",
    fontSize: 14,
    margin: 0,
  },
  fields: {
    alignItems: "end",
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  },
  label: {
    color: "#374151",
    fontSize: 13,
    fontWeight: 700,
    gridColumn: "1 / -1",
  },
  input: {
    border: "1px solid #cbd5e1",
    borderRadius: 6,
    fontSize: 14,
    minHeight: 38,
    padding: "7px 9px",
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
  secondaryButton: {
    ...buttonBase,
    background: "#ffffff",
    border: "1px solid #cbd5e1",
    color: "#374151",
    cursor: "pointer",
  },
  pending: {
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    borderRadius: 6,
    color: "#1d4ed8",
    fontSize: 13,
    fontWeight: 700,
    margin: 0,
    padding: "8px 10px",
  },
  confirm: {
    display: "grid",
    gap: 8,
    gridColumn: "1 / -1",
  },
  confirmText: {
    color: "#374151",
    fontSize: 13,
    lineHeight: 1.45,
    margin: 0,
  },
  confirmActions: {
    display: "flex",
    gap: 8,
  },
  selected: {
    color: "#374151",
    fontSize: 13,
    margin: 0,
    overflowWrap: "anywhere",
  },
  error: {
    background: "#fef2f2",
    border: "1px solid #fecaca",
    borderRadius: 6,
    color: "#7f1d1d",
    fontSize: 14,
    lineHeight: 1.45,
    margin: 0,
    padding: "8px 10px",
  },
} satisfies Record<string, React.CSSProperties>;
