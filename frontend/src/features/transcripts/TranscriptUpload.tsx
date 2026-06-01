"use client";

import { useRef, useState } from "react";

import type { TranscriptMeta } from "../../lib/api/models/TranscriptMeta";
import { uploadSectionTranscript } from "./api/transcripts";

type TranscriptUploadProps = {
  authorization?: string;
  disabled?: boolean;
  initialTranscript?: TranscriptMeta | null;
  moduleId: string;
  onUploaded?: (transcript: TranscriptMeta) => void;
  sectionId: string;
};

export function TranscriptUpload({
  authorization,
  disabled = false,
  initialTranscript = null,
  moduleId,
  onUploaded,
  sectionId,
}: TranscriptUploadProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [transcript, setTranscript] = useState<TranscriptMeta | null>(initialTranscript);
  const [isUploading, setIsUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleFileSelected(file: File) {
    setIsUploading(true);
    setMessage(null);
    try {
      const uploaded = await uploadSectionTranscript(
        moduleId,
        sectionId,
        file,
        authorization,
      );
      setTranscript(uploaded);
      onUploaded?.(uploaded);
    } catch {
      setMessage("Transcript upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <section aria-label="Transcript" style={styles.shell}>
      <div style={styles.status}>
        <span style={styles.label}>Transcript</span>
        {transcript ? (
          <span style={styles.detail}>
            {transcript.originalFileName} · {formatBytes(transcript.fileSize)}
          </span>
        ) : (
          <span style={styles.detail}>No transcript uploaded</span>
        )}
      </div>

      {transcript ? (
        <p aria-live="polite" style={styles.success}>
          Transcript uploaded. Processing is not available yet.
        </p>
      ) : null}

      {message ? (
        <p aria-live="polite" role="status" style={styles.error}>
          {message}
        </p>
      ) : null}

      <button
        disabled={disabled || isUploading || transcript !== null}
        onClick={() => inputRef.current?.click()}
        style={styles.button}
        type="button"
      >
        {isUploading ? "Uploading" : "Upload transcript"}
      </button>
      <input
        accept=".vtt,.txt,text/vtt,text/plain"
        aria-label="Upload transcript"
        disabled={disabled || isUploading || transcript !== null}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (file) {
            void handleFileSelected(file);
          }
        }}
        ref={inputRef}
        style={styles.input}
        type="file"
      />
    </section>
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
  shell: {
    alignItems: "center",
    border: "1px solid #d7dde8",
    borderRadius: 6,
    color: "#111827",
    display: "grid",
    gap: 10,
    padding: 12,
  },
  status: {
    display: "grid",
    gap: 3,
    minWidth: 0,
  },
  label: {
    color: "#111827",
    fontSize: 14,
    fontWeight: 700,
  },
  detail: {
    color: "#4b5563",
    fontSize: 13,
    overflowWrap: "anywhere",
  },
  success: {
    color: "#1f6f35",
    fontSize: 13,
    margin: 0,
  },
  error: {
    color: "#7f1d1d",
    fontSize: 13,
    margin: 0,
  },
  button: {
    background: "#174a63",
    border: "1px solid #174a63",
    borderRadius: 6,
    color: "#ffffff",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 700,
    lineHeight: 1,
    minHeight: 38,
    padding: "0 14px",
    width: "fit-content",
  },
  input: {
    display: "none",
  },
} satisfies Record<string, React.CSSProperties>;
