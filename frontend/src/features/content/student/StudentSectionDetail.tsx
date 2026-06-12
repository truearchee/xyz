"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  type StudentSectionRead,
  type StudentSectionSummariesRead,
  type StudentSummarySlot,
} from "../../../lib/api";
import { ForbiddenError, api } from "../../../lib/api/wrapper";
import { SummaryMarkdown } from "./SummaryMarkdown";

// Reuse the 4.5d backoff (no hard timeout), narrowed to the student summary sub-resource and bounded to
// the `generating` state (§11). A generous wall-clock ceiling — detailed via K2-Think is legitimately
// slow — after which we stop and ask the student to refresh (§10).
const POLL_INITIAL_MS = 1500;
const POLL_MAX_MS = 15_000;
const POLL_BACKOFF = 1.5;
const POLL_WALLCLOCK_CAP_MS = 8 * 60_000;

const GENERATING = "generating";
const READY = "ready";
const UNAVAILABLE = "unavailable";
const NOT_APPLICABLE = "not_applicable";

const blockClass = "grid gap-2 rounded-lg border border-border p-4";
const blockHeadingClass = "m-0 text-xs font-bold uppercase tracking-wide text-text";
const mutedClass = "m-0 text-sm italic text-text-muted";

type ShellState = "loading" | "loaded" | "missing" | "error";

export function StudentSectionDetail({ moduleId, sectionId }: { moduleId: string; sectionId: string }) {
  const [section, setSection] = useState<StudentSectionRead | null>(null);
  const [shellState, setShellState] = useState<ShellState>("loading");

  useEffect(() => {
    let mounted = true;
    setShellState("loading");
    setSection(null);
    void (async () => {
      try {
        const detail = await api.studentSummaries.getSection(sectionId);
        if (!mounted) return;
        setSection(detail);
        setShellState("loaded");
      } catch (caught) {
        if (!mounted) return;
        // 404 (rows D/P/I) and 403 are both "you cannot see this" — never leak which.
        if (caught instanceof ForbiddenError || (caught instanceof ApiError && caught.status === 404)) {
          setShellState("missing");
        } else {
          setShellState("error");
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, [sectionId]);

  if (shellState === "loading") {
    return (
      <section aria-busy="true" className="rounded-lg border border-border p-6">
        <h1 className="m-0 font-display text-lg leading-snug text-text">Loading section…</h1>
      </section>
    );
  }
  if (shellState === "missing") {
    return (
      <section aria-label="Section unavailable" className="rounded-lg border border-border p-6">
        <h1 className="m-0 font-display text-lg leading-snug text-text">This section is unavailable</h1>
        <p className="mt-2 text-sm leading-normal text-text-muted">It may be unpublished or you may not have access.</p>
      </section>
    );
  }
  if (shellState === "error" || section === null) {
    return (
      <section role="alert" className="rounded-lg border border-danger p-6 text-danger-text">
        <h1 className="m-0 font-display text-lg leading-snug">Couldn’t load this section</h1>
        <p className="mt-2 text-sm leading-normal">Please refresh to try again.</p>
      </section>
    );
  }

  return (
    <section aria-labelledby="student-section-title" data-testid="student-section-detail" className="grid gap-5">
      <header>
        <p className="m-0 mb-1 text-xs font-bold uppercase text-text-muted">{section.type}</p>
        <h1 id="student-section-title" className="m-0 font-display text-2xl leading-tight text-text">
          {section.title}
        </h1>
      </header>

      <section aria-label="Lecturer notes" className={blockClass}>
        <h2 className={blockHeadingClass}>Lecturer notes</h2>
        {section.lecturerNotes ? (
          <p className="m-0 text-sm leading-normal text-text">{section.lecturerNotes}</p>
        ) : (
          <p className={mutedClass}>No lecturer notes</p>
        )}
      </section>

      <section aria-label="Learning materials" className={blockClass}>
        <h2 className={blockHeadingClass}>Learning materials</h2>
        {section.materials.length === 0 ? (
          <p className={mutedClass}>No materials</p>
        ) : (
          <ul className="m-0 grid list-disc gap-1 pl-[18px] text-text">
            {section.materials.map((m) => (
              <li key={m.id} className="text-sm leading-normal text-text">
                {m.fileName}
              </li>
            ))}
          </ul>
        )}
      </section>

      <SummariesPanel sectionId={sectionId} />
    </section>
  );
}

function SummariesPanel({ sectionId }: { sectionId: string }) {
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
        <h2 className={blockHeadingClass}>Summaries</h2>
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
      <h3 className="m-0 text-sm font-bold text-text-muted">{label}</h3>
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
