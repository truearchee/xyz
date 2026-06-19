"use client";

import { useEffect, useState } from "react";

import {
  type DetailedSummaryContent,
  type TranscriptSummariesRead,
} from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";

// Backoff polling, no hard timeout — same rationale as the status badge (4.5d §5). Brief and
// detailed render INDEPENDENTLY as each lands (brief generally first).
const POLL_INITIAL_MS = 1500;
const POLL_MAX_MS = 15_000;
const POLL_BACKOFF = 1.5;
const ACTIVE_STEP_STATES = new Set(["queued", "running"]);

type TranscriptSummaryPanelProps = {
  moduleId: string;
  sectionId: string;
  sectionKey: string;
  transcriptId: string;
};

export function TranscriptSummaryPanel({
  moduleId,
  sectionId,
  sectionKey,
  transcriptId,
}: TranscriptSummaryPanelProps) {
  const [summaries, setSummaries] = useState<TranscriptSummariesRead | null>(null);

  useEffect(() => {
    setSummaries(null);

    let isMounted = true;
    let timeoutId = 0;
    let delay = POLL_INITIAL_MS;

    const tick = async (): Promise<void> => {
      let settled = false;
      try {
        const next = await api.transcripts.getSummaries(moduleId, sectionId);
        if (!isMounted) {
          return;
        }
        setSummaries(next);
        settled = isSettled(next);
      } catch {
        // Transient (or transcript missing) — keep polling with backoff; the badge owns the
        // missing-transcript transition, so we simply retry.
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
  }, [moduleId, sectionId, transcriptId]);

  if (summaries === null) {
    return null;
  }

  const briefStep = summaries.status.steps.summaryBrief.status;
  const detailedStep = summaries.status.steps.summaryDetailed.status;
  const failureMessage = summaries.status.safeFailureMessage ?? "Summary generation failed.";

  return (
    <section
      aria-label="Lecture summaries"
      data-testid={`section-summary-panel-${sectionKey}`}
      className="grid gap-3"
    >
      <div className="grid gap-1.5">
        <h4 className="m-0 text-sm font-semibold uppercase tracking-wide text-text">Brief summary</h4>
        {summaries.brief ? (
          <p
            data-testid={`section-summary-brief-${sectionKey}`}
            className="m-0 text-sm leading-normal text-text"
          >
            {summaries.brief.text}
          </p>
        ) : (
          <SummaryPlaceholder
            label="brief"
            sectionKey={sectionKey}
            stepStatus={briefStep}
            failureMessage={failureMessage}
            notStartedText="Brief summary not generated."
          />
        )}
      </div>

      <div className="grid gap-1.5">
        <h4 className="m-0 text-sm font-semibold uppercase tracking-wide text-text">Detailed study summary</h4>
        {summaries.detailed ? (
          <DetailedSummaryView
            detailed={summaries.detailed}
            sectionKey={sectionKey}
          />
        ) : (
          <SummaryPlaceholder
            label="detailed"
            sectionKey={sectionKey}
            stepStatus={detailedStep}
            failureMessage={failureMessage}
            notStartedText="Detailed summary not generated."
          />
        )}
      </div>
    </section>
  );
}

function SummaryPlaceholder({
  label,
  sectionKey,
  stepStatus,
  failureMessage,
  notStartedText,
}: {
  label: string;
  sectionKey: string;
  stepStatus: string;
  failureMessage: string;
  notStartedText: string;
}) {
  const failed = stepStatus === "failed";
  const generating = ACTIVE_STEP_STATES.has(stepStatus);
  const text = failed
    ? failureMessage
    : generating
      ? "Generating…"
      : notStartedText;
  return (
    <p
      data-testid={`section-summary-${label}-status-${sectionKey}`}
      role={failed ? "alert" : "status"}
      className={
        failed
          ? "m-0 rounded-md border border-danger bg-danger-surface px-2.5 py-2 text-sm leading-snug text-danger-text"
          : "m-0 text-sm italic text-text-muted"
      }
    >
      {text}
    </p>
  );
}

function DetailedSummaryView({
  detailed,
  sectionKey,
}: {
  detailed: DetailedSummaryContent;
  sectionKey: string;
}) {
  return (
    <div
      data-testid={`section-summary-detailed-${sectionKey}`}
      className="grid gap-3 rounded-lg border border-border p-3"
    >
      <DetailedSection title="Overview">
        <p className="m-0 text-sm leading-normal text-text">{detailed.overview}</p>
      </DetailedSection>
      <DetailedSection title="Key concepts">
        <BulletList items={detailed.keyConcepts} />
      </DetailedSection>
      <DetailedSection title="Important definitions">
        <dl className="m-0 grid gap-1.5">
          {detailed.importantDefinitions.map((definition, index) => (
            <div key={index} className="grid gap-0.5">
              <dt className="m-0 text-sm font-semibold text-text">{definition.term}</dt>
              <dd className="m-0 text-sm leading-normal text-text-muted">{definition.definition}</dd>
            </div>
          ))}
        </dl>
      </DetailedSection>
      <DetailedSection title="Main explanations">
        <BulletList items={detailed.mainExplanations} />
      </DetailedSection>
      <DetailedSection title="Examples">
        <BulletList items={detailed.examples} />
      </DetailedSection>
      <DetailedSection title="Exam-relevant points">
        <BulletList items={detailed.examRelevantPoints} />
      </DetailedSection>
      {detailed.labNotes && detailed.labNotes.length > 0 ? (
        <DetailedSection title="Lab notes">
          <BulletList items={detailed.labNotes} />
        </DetailedSection>
      ) : null}
    </div>
  );
}

function DetailedSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1">
      <h5 className="m-0 text-sm font-semibold text-text-muted">{title}</h5>
      {children}
    </div>
  );
}

function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="m-0 grid list-disc gap-1 pl-[18px] text-text">
      {items.map((item, index) => (
        <li key={index} className="m-0 text-sm leading-normal text-text">
          {item}
        </li>
      ))}
    </ul>
  );
}

function isSettled(summaries: TranscriptSummariesRead): boolean {
  const state = summaries.status.overallState;
  if (state === "failed" || state === "summarized") {
    return true;
  }
  if (state === "summarizing") {
    const { summaryBrief, summaryDetailed } = summaries.status.steps;
    return !(
      ACTIVE_STEP_STATES.has(summaryBrief.status) ||
      ACTIVE_STEP_STATES.has(summaryDetailed.status)
    );
  }
  return false;
}
