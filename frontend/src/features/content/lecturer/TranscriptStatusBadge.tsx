"use client";

import { useEffect, useState } from "react";

import { ApiError, type TranscriptMeta } from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";

const TERMINAL_STATUSES = new Set(["completed", "failed"]);
const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 60_000;

type TranscriptStatusBadgeProps = {
  moduleId: string;
  onTranscriptMissing: () => void;
  onTranscriptChange: (transcript: TranscriptMeta) => void;
  sectionId: string;
  sectionKey: string;
  transcript: TranscriptMeta;
};

export function TranscriptStatusBadge({
  moduleId,
  onTranscriptMissing,
  onTranscriptChange,
  sectionId,
  sectionKey,
  transcript,
}: TranscriptStatusBadgeProps) {
  const [hasTimedOut, setHasTimedOut] = useState(false);

  useEffect(() => {
    setHasTimedOut(false);

    if (TERMINAL_STATUSES.has(transcript.status)) {
      return;
    }

    let isMounted = true;
    const startedAt = Date.now();

    const intervalId = window.setInterval(() => {
      if (Date.now() - startedAt >= POLL_TIMEOUT_MS) {
        window.clearInterval(intervalId);
        if (isMounted) {
          setHasTimedOut(true);
        }
        return;
      }

      void api.transcripts
        .getActive(moduleId, sectionId)
        .then((updatedTranscript) => {
          if (!isMounted) {
            return;
          }
          onTranscriptChange(updatedTranscript);
          if (TERMINAL_STATUSES.has(updatedTranscript.status)) {
            window.clearInterval(intervalId);
          }
        })
        .catch((caught) => {
          if (isTranscriptNotFound(caught)) {
            if (isMounted) {
              onTranscriptMissing();
            }
            window.clearInterval(intervalId);
            return;
          }

          if (isMounted) {
            setHasTimedOut(true);
          }
          window.clearInterval(intervalId);
        });
    }, POLL_INTERVAL_MS);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, [
    moduleId,
    onTranscriptChange,
    onTranscriptMissing,
    sectionId,
    transcript.id,
    transcript.status,
  ]);

  const text = hasTimedOut
    ? "Processing is taking longer than expected. Refresh to check again."
    : statusText(transcript.status);

  return (
    <p
      aria-live="polite"
      data-testid={`section-transcript-status-${sectionKey}`}
      role="status"
      style={
        hasTimedOut
          ? styles.timeout
          : transcript.status === "completed"
            ? styles.completed
            : transcript.status === "failed"
              ? styles.failed
              : styles.processing
      }
    >
      {text}
    </p>
  );
}

function isTranscriptNotFound(caught: unknown): boolean {
  return (
    caught instanceof ApiError &&
    caught.status === 404 &&
    caught.body?.detail === "TRANSCRIPT_NOT_FOUND"
  );
}

function statusText(status: string): string {
  if (status === "completed") {
    return "Transcript processing completed";
  }
  if (status === "failed") {
    return "Transcript processing failed";
  }
  return `Transcript status: ${status}`;
}

const statusBase = {
  borderRadius: 6,
  fontSize: 14,
  fontWeight: 700,
  lineHeight: 1.45,
  margin: 0,
  padding: "8px 10px",
} satisfies React.CSSProperties;

const styles = {
  completed: {
    ...statusBase,
    background: "#ecfdf5",
    border: "1px solid #a7f3d0",
    color: "#047857",
  },
  failed: {
    ...statusBase,
    background: "#fef2f2",
    border: "1px solid #fecaca",
    color: "#7f1d1d",
  },
  processing: {
    ...statusBase,
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    color: "#1d4ed8",
  },
  timeout: {
    ...statusBase,
    background: "#fffbeb",
    border: "1px solid #fde68a",
    color: "#92400e",
  },
} satisfies Record<string, React.CSSProperties>;
