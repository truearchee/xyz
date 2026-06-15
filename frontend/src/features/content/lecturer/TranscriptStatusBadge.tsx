"use client";

import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  type TranscriptMeta,
  type TranscriptProcessingStatus,
} from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { cn } from "../../../components/ui/cn";

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
  const [isRetrying, setIsRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  // Keep the missing-callback in a ref so its identity changing never restarts polling.
  const onMissingRef = useRef(onTranscriptMissing);
  onMissingRef.current = onTranscriptMissing;

  async function onRetry() {
    if (processingStatus === null) {
      return;
    }
    setIsRetrying(true);
    setRetryError(null);
    try {
      const status = await api.transcripts.retry(
        moduleId,
        sectionId,
        processingStatus.activeTranscriptId,
      );
      setProcessingStatus(status);
      setRetryNonce((nonce) => nonce + 1); // restart polling on the resumed pipeline
    } catch (caught) {
      setRetryError(errorMessage(caught));
    } finally {
      setIsRetrying(false);
    }
  }

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
  }, [moduleId, sectionId, transcript.id, retryNonce]);

  const text = statusText(processingStatus, transcript.status);
  const statusKind = statusStyleKind(processingStatus, transcript.status);
  const canRetry =
    processingStatus !== null &&
    processingStatus.overallState === "failed" &&
    processingStatus.retryable;

  return (
    <div className="grid gap-2">
      <p
        aria-live="polite"
        data-testid={`section-transcript-status-${sectionKey}`}
        role="status"
        className={cn(statusBaseClass, STATUS_KIND_CLASS[statusKind])}
      >
        {text}
      </p>
      {processingStatus !== null ? (
        <StepStates
          failedStep={processingStatus.failedStep}
          sectionKey={sectionKey}
          steps={processingStatus.steps}
        />
      ) : null}
      {canRetry ? (
        <button
          data-testid={`section-transcript-retry-${sectionKey}`}
          disabled={isRetrying}
          onClick={() => void onRetry()}
          className={cn(
            "min-h-[38px] justify-self-start rounded-full border px-3.5 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2",
            isRetrying
              ? "cursor-not-allowed border-border bg-surface-muted text-text-muted"
              : "border-primary bg-primary text-on-primary hover:bg-primary-hover",
          )}
          type="button"
        >
          {isRetrying ? "Retrying…" : "Retry failed processing"}
        </button>
      ) : null}
      {retryError ? (
        <p role="alert" className={cn(statusBaseClass, STATUS_KIND_CLASS.failed)}>
          {retryError}
        </p>
      ) : null}
    </div>
  );
}

const STEP_LABELS: Array<{ key: keyof TranscriptProcessingStatus["steps"]; label: string }> = [
  { key: "parse", label: "Parse" },
  { key: "chunk", label: "Chunk" },
  { key: "embed", label: "Embed" },
  { key: "summaryBrief", label: "Brief" },
  { key: "summaryDetailed", label: "Detailed" },
];

function StepStates({
  failedStep,
  sectionKey,
  steps,
}: {
  failedStep: string | null;
  sectionKey: string;
  steps: TranscriptProcessingStatus["steps"];
}) {
  return (
    <ul
      data-testid={`section-transcript-steps-${sectionKey}`}
      className="m-0 flex list-none flex-wrap gap-2 p-0"
    >
      {STEP_LABELS.map(({ key, label }) => {
        const status = steps[key].status;
        return (
          <li
            key={key}
            className="flex items-center gap-1.5 rounded-full border border-border bg-surface-muted px-2 py-1 text-xs"
          >
            <span className="font-semibold text-text">{label}</span>
            <span className={cn("font-semibold", stepStatusClass(status))}>{stepStatusText(status)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function stepStatusText(status: string): string {
  if (status === "completed") return "completed";
  if (status === "failed") return "failed";
  if (status === "running") return "running";
  if (status === "queued") return "retrying";
  return "—";
}

function stepStatusClass(status: string): string {
  if (status === "failed") return "text-danger-text";
  if (status === "completed") return "text-success-text";
  if (status === "running" || status === "queued") return "text-info-text";
  return "text-text-muted";
}

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
  return "Unexpected error";
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
): keyof typeof STATUS_KIND_CLASS {
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

// Token-based status pill classes (the tonal pairs — AA-safe at body size; status by text label, not
// color alone). statusBaseClass is the shared shape; STATUS_KIND_CLASS the per-kind tonal tokens.
const statusBaseClass = "m-0 rounded-md border px-2.5 py-2 text-sm font-semibold leading-snug";

const STATUS_KIND_CLASS = {
  completed: "bg-success-surface border-success text-success-text",
  failed: "bg-danger-surface border-danger text-danger-text",
  processing: "bg-info-surface border-info text-info-text",
} as const;
