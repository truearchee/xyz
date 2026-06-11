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
      setTranscript(uploadedTranscript);
      setSelectedFile(null);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    } catch (caught) {
      if (isTranscriptAlreadyExists(caught)) {
        await loadActiveTranscript();
        setError("This section already has an active transcript.");
      } else {
        setError(errorMessage(caught));
      }
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
          <TranscriptSummaryPanel
            moduleId={moduleId}
            sectionId={sectionId}
            sectionKey={sectionKey}
            transcriptId={transcript.id}
          />
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

function isTranscriptAlreadyExists(caught: unknown): boolean {
  return (
    caught instanceof ApiError &&
    caught.status === 409 &&
    detailCode(caught) === "TRANSCRIPT_ALREADY_EXISTS"
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
