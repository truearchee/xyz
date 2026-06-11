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
      style={styles.shell}
    >
      <div style={styles.block}>
        <h4 style={styles.heading}>Brief summary</h4>
        {summaries.brief ? (
          <p
            data-testid={`section-summary-brief-${sectionKey}`}
            style={styles.briefText}
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

      <div style={styles.block}>
        <h4 style={styles.heading}>Detailed study summary</h4>
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
      style={failed ? styles.failure : styles.placeholder}
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
      style={styles.detailed}
    >
      <DetailedSection title="Overview">
        <p style={styles.bodyText}>{detailed.overview}</p>
      </DetailedSection>
      <DetailedSection title="Key concepts">
        <BulletList items={detailed.keyConcepts} />
      </DetailedSection>
      <DetailedSection title="Important definitions">
        <dl style={styles.definitionList}>
          {detailed.importantDefinitions.map((definition, index) => (
            <div key={index} style={styles.definitionRow}>
              <dt style={styles.definitionTerm}>{definition.term}</dt>
              <dd style={styles.definitionBody}>{definition.definition}</dd>
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
    <div style={styles.detailedSection}>
      <h5 style={styles.detailedHeading}>{title}</h5>
      {children}
    </div>
  );
}

function BulletList({ items }: { items: string[] }) {
  return (
    <ul style={styles.list}>
      {items.map((item, index) => (
        <li key={index} style={styles.bodyText}>
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

const styles = {
  shell: {
    display: "grid",
    gap: 12,
  },
  block: {
    display: "grid",
    gap: 6,
  },
  heading: {
    color: "#111827",
    fontSize: 14,
    fontWeight: 700,
    margin: 0,
    textTransform: "uppercase",
    letterSpacing: "0.03em",
  },
  briefText: {
    color: "#111827",
    fontSize: 14,
    lineHeight: 1.5,
    margin: 0,
  },
  placeholder: {
    color: "#4b5563",
    fontSize: 14,
    fontStyle: "italic",
    margin: 0,
  },
  failure: {
    background: "#fef2f2",
    border: "1px solid #fecaca",
    borderRadius: 6,
    color: "#7f1d1d",
    fontSize: 14,
    lineHeight: 1.45,
    margin: 0,
    padding: "8px 10px",
  },
  detailed: {
    border: "1px solid #d7dde8",
    borderRadius: 8,
    display: "grid",
    gap: 12,
    padding: 12,
  },
  detailedSection: {
    display: "grid",
    gap: 4,
  },
  detailedHeading: {
    color: "#374151",
    fontSize: 13,
    fontWeight: 700,
    margin: 0,
  },
  bodyText: {
    color: "#111827",
    fontSize: 14,
    lineHeight: 1.5,
    margin: 0,
  },
  list: {
    color: "#111827",
    display: "grid",
    gap: 4,
    margin: 0,
    paddingLeft: 18,
  },
  definitionList: {
    display: "grid",
    gap: 6,
    margin: 0,
  },
  definitionRow: {
    display: "grid",
    gap: 2,
  },
  definitionTerm: {
    color: "#111827",
    fontSize: 14,
    fontWeight: 700,
    margin: 0,
  },
  definitionBody: {
    color: "#374151",
    fontSize: 14,
    lineHeight: 1.5,
    margin: 0,
  },
} satisfies Record<string, React.CSSProperties>;
