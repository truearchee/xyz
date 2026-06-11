"use client";

import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  type TranscriptMeta,
  type TranscriptProcessingStatus,
} from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";

// Stage 4.5d: backoff polling, NO hard timeout. The pipeline now runs through summary generation
// (brief then detailed); detailed + queue wait + provider 429 backoff routinely exceed 60s, so a
// 60s "stuck" timeout was wrong. We poll with a growing-but-capped interval until the pipeline is
// quiescent, and show a passive "Generating…" state rather than a spinner that implies stuck.
const POLL_INITIAL_MS = 1500;
const POLL_MAX_MS = 15_000;
const POLL_BACKOFF = 1.5;
const ACTIVE_STEP_STATES = new Set(["queued", "running"]);

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
  const [processingStatus, setProcessingStatus] =
    useState<TranscriptProcessingStatus | null>(null);
  // Keep the missing-callback in a ref so its identity changing never restarts polling.
  const onMissingRef = useRef(onTranscriptMissing);
  onMissingRef.current = onTranscriptMissing;

  useEffect(() => {
    setProcessingStatus(null);

    let isMounted = true;
    let timeoutId = 0;
    let delay = POLL_INITIAL_MS;

    const tick = async (): Promise<void> => {
      let settled = false;
      try {
        const status = await api.transcripts.getProcessingStatus(
          moduleId,
          sectionId,
        );
        if (!isMounted) {
          return;
        }
        setProcessingStatus(status);
        settled = isSettled(status);
      } catch (caught) {
        if (isTranscriptNotFound(caught)) {
          if (isMounted) {
            onMissingRef.current();
          }
          return;
        }
        // Transient error: keep polling with backoff (no hard timeout). Last known status stays.
      }

      if (!isMounted || settled) {
        return;
      }
      delay = Math.min(Math.round(delay * POLL_BACKOFF), POLL_MAX_MS);
      timeoutId = window.setTimeout(() => void tick(), delay);
    };

    void tick();

    return () => {
      isMounted = false;
      window.clearTimeout(timeoutId);
    };
  }, [moduleId, sectionId, transcript.id]);

  const text = statusText(processingStatus, transcript.status);
  const statusKind = statusStyleKind(processingStatus, transcript.status);

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

// The pipeline is quiescent (stop polling) when it has failed, fully summarized, or reached the
// brief-only resting state: 'summarizing' with no summary step still queued/running (detailed is
// either disabled — not_started — or already done). Earlier phases keep polling.
function isSettled(status: TranscriptProcessingStatus): boolean {
  if (status.overallState === "failed" || status.overallState === "summarized") {
    return true;
  }
  if (status.overallState === "summarizing") {
    const { summaryBrief, summaryDetailed } = status.steps;
    const stillWorking =
      ACTIVE_STEP_STATES.has(summaryBrief.status) ||
      ACTIVE_STEP_STATES.has(summaryDetailed.status);
    return !stillWorking;
  }
  return false;
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
  if (processingStatus.overallState === "summarized") {
    return "Summaries ready";
  }
  if (processingStatus.overallState === "summarizing") {
    return "Generating summaries…";
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
  processingStatus: TranscriptProcessingStatus | null,
  fallbackTranscriptStatus: string,
): keyof typeof styles {
  if (
    processingStatus?.overallState === "failed" ||
    fallbackTranscriptStatus === "failed"
  ) {
    return "failed";
  }
  if (processingStatus !== null && processingStatus.overallState === "summarized") {
    return "completed";
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
} satisfies Record<string, React.CSSProperties>;
