"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  type TranscriptMeta,
  type TranscriptProcessingStatus,
} from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";

const TERMINAL_STATES = new Set(["embedded", "failed"]);
const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 60_000;

type TranscriptStatusBadgeProps = {
  moduleId: string;
  onTranscriptMissing: () => void;
  sectionId: string;
  sectionKey: string;
  transcript: TranscriptMeta;
};

export function TranscriptStatusBadge({
  moduleId,
  onTranscriptMissing,
  sectionId,
  sectionKey,
  transcript,
}: TranscriptStatusBadgeProps) {
  const [hasTimedOut, setHasTimedOut] = useState(false);
  const [processingStatus, setProcessingStatus] =
    useState<TranscriptProcessingStatus | null>(null);

  useEffect(() => {
    setHasTimedOut(false);
    setProcessingStatus(null);

    let isMounted = true;
    const startedAt = Date.now();

    const loadStatus = async (): Promise<boolean> => {
      if (Date.now() - startedAt >= POLL_TIMEOUT_MS) {
        if (isMounted) {
          setHasTimedOut(true);
        }
        return true;
      }

      try {
        const updatedStatus = await api.transcripts.getProcessingStatus(
          moduleId,
          sectionId,
        );
        if (!isMounted) {
          return true;
        }
        setProcessingStatus(updatedStatus);
        return TERMINAL_STATES.has(updatedStatus.overallState);
      } catch (caught) {
        if (isTranscriptNotFound(caught)) {
          if (isMounted) {
            onTranscriptMissing();
          }
          return true;
        }

        if (isMounted) {
          setHasTimedOut(true);
        }
        return true;
      }
    };

    void loadStatus();
    const intervalId = window.setInterval(() => {
      void loadStatus().then((shouldStop) => {
        if (shouldStop) {
          window.clearInterval(intervalId);
        }
      });
    }, POLL_INTERVAL_MS);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, [
    moduleId,
    onTranscriptMissing,
    sectionId,
    transcript.id,
  ]);

  const text = hasTimedOut
    ? "Processing is taking longer than expected. Refresh to check again."
    : statusText(processingStatus, transcript.status);
  const statusKind = statusStyleKind(
    hasTimedOut,
    processingStatus,
    transcript.status,
  );

  return (
    <p
      aria-live="polite"
      data-testid={`section-transcript-status-${sectionKey}`}
      role="status"
      style={styles[statusKind]}
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

function statusText(
  processingStatus: TranscriptProcessingStatus | null,
  fallbackTranscriptStatus: string,
): string {
  if (processingStatus === null) {
    return transcriptStatusText(fallbackTranscriptStatus);
  }

  if (processingStatus.overallState === "failed") {
    return processingStatus.safeFailureMessage ?? "Failed";
  }
  if (isEmbedded(processingStatus)) {
    return "Embedded";
  }
  if (
    processingStatus.overallState === "embedding" ||
    processingStatus.steps.embed.status === "running"
  ) {
    return "Embedding";
  }
  if (
    processingStatus.overallState === "chunking" ||
    processingStatus.steps.chunk.status === "running"
  ) {
    return "Chunking";
  }
  if (
    processingStatus.overallState === "parsing" ||
    processingStatus.steps.parse.status === "running"
  ) {
    return "Parsing";
  }
  if (processingStatus.overallState === "chunked") {
    return "Chunked";
  }
  if (processingStatus.overallState === "parsed") {
    return "Parsed";
  }
  if (processingStatus.overallState === "queued") {
    return "Queued";
  }
  if (processingStatus.overallState === "uploaded") {
    return "Uploaded";
  }
  if (processingStatus.currentPhase) {
    return formatStatusLabel(processingStatus.currentPhase);
  }
  return formatStatusLabel(processingStatus.overallState);
}

function transcriptStatusText(status: string): string {
  if (status === "failed") {
    return "Failed";
  }
  return formatStatusLabel(status);
}

function statusStyleKind(
  hasTimedOut: boolean,
  processingStatus: TranscriptProcessingStatus | null,
  fallbackTranscriptStatus: string,
): keyof typeof styles {
  if (hasTimedOut) {
    return "timeout";
  }
  if (processingStatus !== null && isEmbedded(processingStatus)) {
    return "completed";
  }
  if (
    processingStatus?.overallState === "failed" ||
    fallbackTranscriptStatus === "failed"
  ) {
    return "failed";
  }
  if (processingStatus === null && fallbackTranscriptStatus === "completed") {
    return "completed";
  }
  return "processing";
}

function isEmbedded(processingStatus: TranscriptProcessingStatus): boolean {
  return (
    processingStatus.overallState === "embedded" &&
    processingStatus.steps.embed.status === "completed"
  );
}

function formatStatusLabel(status: string): string {
  if (status.length === 0) {
    return "Queued";
  }
  return status
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
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
