"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  type StudentSectionSummariesRead,
  type StudentSummarySlot,
} from "../../../lib/api";
import { api } from "../../../lib/api/wrapper";
import { SummaryMarkdown } from "./SummaryMarkdown";

// Post-4.9 Workstream B: extracted VERBATIM from StudentSectionDetail's SummariesPanel/SummarySlot so the
// brief + detailed summaries render inline inside each section block on the module page (no separate page).
// Logic unchanged — same bounded polling (no hard timeout, §11), wall-clock ceiling (§10), unmount-safe
// cleanup, and §4.3 generating/unavailable states. Each section block mounts its own instance (independent
// poller; a module has few sections, each backs off + caps).
const POLL_INITIAL_MS = 1500;
const POLL_MAX_MS = 15_000;
const POLL_BACKOFF = 1.5;
const POLL_WALLCLOCK_CAP_MS = 8 * 60_000;

const GENERATING = "generating";
const READY = "ready";
const NOT_APPLICABLE = "not_applicable";

const blockClass = "grid gap-2 rounded-lg border border-border p-4";
const blockHeadingClass = "m-0 text-xs font-bold uppercase tracking-wide text-text";
const mutedClass = "m-0 text-sm italic text-text-muted";

export function SectionSummaries({ sectionId }: { sectionId: string }) {
  const [summaries, setSummaries] = useState<StudentSectionSummariesRead | null>(null);
  const [readError, setReadError] = useState(false);
  const [capped, setCapped] = useState(false);
  const startedAt = useRef<number>(0);

  const renderedGenerating = useCallback((data: StudentSectionSummariesRead | null): boolean => {
    if (!data) return false;
    return data.summaries.brief.state === GENERATING || data.summaries.detailed.state === GENERATING;
  }, []);

  useEffect(() => {
    let mounted = true;
    let timeoutId = 0;
    let delay = POLL_INITIAL_MS;
    startedAt.current = 0;
    setSummaries(null);
    setReadError(false);
    setCapped(false);

    const tick = async (): Promise<void> => {
      try {
        const next = await api.studentSummaries.getSummaries(sectionId);
        if (!mounted) return;
        setSummaries(next);
        setReadError(false);
        if (!renderedGenerating(next)) {
          return; // all slots terminal — stop polling
        }
      } catch {
        if (!mounted) return;
        setReadError(true);
        // transient — keep polling with backoff
      }
      if (!mounted) return;
      // Wall-clock cap: detailed generation is legitimately slow; stop and ask for a refresh.
      if (startedAt.current === 0) {
        // first scheduled poll establishes the clock baseline (Date.now is fine in the browser)
        startedAt.current = Date.now();
      } else if (Date.now() - startedAt.current > POLL_WALLCLOCK_CAP_MS) {
        setCapped(true);
        return;
      }
      delay = Math.min(Math.round(delay * POLL_BACKOFF), POLL_MAX_MS);
      timeoutId = window.setTimeout(() => void tick(), delay);
    };

    void tick();
    return () => {
      mounted = false;
      window.clearTimeout(timeoutId); // no leaked intervals on unmount
    };
  }, [sectionId, renderedGenerating]);

  if (summaries === null) {
    return (
      <section aria-busy={!readError} aria-label="Summaries" className={blockClass}>
        <h3 className={blockHeadingClass}>Summaries</h3>
        {readError ? (
          <p role="alert" className={mutedClass}>
            Couldn’t load summaries — refresh to try again.
          </p>
        ) : (
          <p className={mutedClass}>Loading summaries…</p>
        )}
      </section>
    );
  }

  return (
    <section aria-label="Summaries" className={blockClass}>
      <SummarySlot label="Brief summary" testId="student-summary-brief" slot={summaries.summaries.brief} capped={capped} />
      <SummarySlot
        label="Detailed study summary"
        testId="student-summary-detailed"
        slot={summaries.summaries.detailed}
        capped={capped}
      />
    </section>
  );
}

function SummarySlot({
  label,
  testId,
  slot,
  capped,
}: {
  label: string;
  testId: string;
  slot: StudentSummarySlot;
  capped: boolean;
}) {
  if (slot.state === NOT_APPLICABLE) {
    return null; // block absent for non-lecture/lab
  }
  return (
    <div data-testid={testId} data-state={slot.state} className="grid gap-1.5">
      <h4 className="m-0 text-sm font-bold text-text-muted">{label}</h4>
      {slot.state === READY && slot.truncated ? (
        // F-4.5-50: truncation is never silent — the student sees that this covers only the first portion.
        <p data-testid={`${testId}-truncated`} className="m-0 flex items-center gap-1.5 text-xs text-warning-text">
          <span aria-hidden className="inline-block size-1.5 rounded-full bg-warning" />
          Based on the first portion of the transcript.
        </p>
      ) : null}
      {slot.state === READY && slot.content ? (
        <SummaryMarkdown content={slot.content} testId={`${testId}-content`} />
      ) : slot.state === GENERATING ? (
        <p role="status" className={mutedClass}>
          {capped ? "Still being generated — refresh to check." : "Summary is being generated."}
        </p>
      ) : (
        <p role="status" className={mutedClass}>
          Summary is currently unavailable.
        </p>
      )}
    </div>
  );
}
