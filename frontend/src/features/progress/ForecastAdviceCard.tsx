"use client";

import { useEffect, useState } from "react";

import type { ForecastAdviceRead } from "../../lib/api";
import { api } from "../../lib/api/wrapper";

type ForecastAdviceCardProps = {
  moduleId: string;
};

type LoadState = "loading" | "ready" | "error";

// Backoff poll (no hard timeout, capped) per the codebase async convention. The deterministic/template
// advice renders immediately; the AI rephrase swaps in within an aria-live region when ready.
const POLL_INITIAL_MS = 1500;
const POLL_MAX_MS = 6000;
const POLL_BACKOFF = 1.6;
const POLL_WALL_CLOCK_MS = 30000;

export function ForecastAdviceCard({ moduleId }: ForecastAdviceCardProps) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [advice, setAdvice] = useState<ForecastAdviceRead | null>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const startedAt = Date.now();
    let delay = POLL_INITIAL_MS;

    setLoadState("loading");
    setAdvice(null);

    const tick = async () => {
      try {
        const next = await api.analytics.getStudentForecastAdvice(moduleId);
        if (!active) return;
        setAdvice(next);
        setLoadState("ready");
        // Keep polling only while the AI is still being prepared, bounded by a wall-clock cap.
        if (next.aiStatus === "queued" && Date.now() - startedAt < POLL_WALL_CLOCK_MS) {
          timer = setTimeout(() => void tick(), delay);
          delay = Math.min(Math.round(delay * POLL_BACKOFF), POLL_MAX_MS);
        }
      } catch {
        if (!active) return;
        setLoadState("error");
      }
    };

    void tick();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [moduleId]);

  const pending = advice?.aiStatus === "queued";
  const bodyText =
    loadState === "error" ? "This view is not available right now." : (advice?.text ?? "");

  // One consistent shell across loading → template → AI swap, so the aria-live region is always present
  // (the initial template and the AI rephrase both announce) and the reserved text height never shifts
  // the cards below (incl. gamification). Tone-neutral for every forecast state (incl. impossible) — the
  // ForecastPanel badge already carries the one status colour; this card is the supportive next move.
  return (
    <section
      aria-label="Grade advice"
      aria-busy={loadState === "loading" || pending}
      data-testid="forecast-advice-card"
      data-source={advice?.source ?? ""}
      data-ai-status={advice?.aiStatus ?? ""}
      data-forecast-state={advice?.forecastState ?? ""}
      className="grid gap-2 rounded-lg border border-border bg-surface-raised p-4"
    >
      <div>
        <p className="m-0 mb-1 text-xs font-medium uppercase text-text-muted">Your next step</p>
        <h2 className="m-0 font-display text-base leading-snug text-text">Grade advice</h2>
      </div>
      <p
        aria-live="polite"
        data-testid="forecast-advice-text"
        className="m-0 min-h-[3.5rem] text-sm leading-normal text-text"
      >
        {bodyText}
      </p>
      {pending ? (
        <p data-testid="forecast-advice-pending" className="m-0 text-xs italic text-text-muted">
          Preparing advice…
        </p>
      ) : null}
    </section>
  );
}
