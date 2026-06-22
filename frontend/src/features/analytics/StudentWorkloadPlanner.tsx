"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { ApiError, type StudentAvailabilityRead, type WorkloadPlanRead } from "../../lib/api";
import { api } from "../../lib/api/wrapper";

type StudentWorkloadPlannerProps = {
  moduleId: string;
  compact?: boolean;
};

type LoadState = "loading" | "ready" | "error";

const DAY_OPTIONS = [
  ["monday", "Mon"],
  ["tuesday", "Tue"],
  ["wednesday", "Wed"],
  ["thursday", "Thu"],
  ["friday", "Fri"],
  ["saturday", "Sat"],
  ["sunday", "Sun"],
] as const;

const WINDOW_OPTIONS = [
  ["morning", "Morning"],
  ["afternoon", "Afternoon"],
  ["evening", "Evening"],
  ["no_preference", "Any"],
] as const;

function isMissingPlan(caught: unknown): boolean {
  return caught instanceof ApiError && caught.status === 404;
}

function message(caught: unknown): string {
  if (caught instanceof ApiError) {
    const detail = caught.body?.detail;
    return typeof detail === "string" ? detail : caught.message;
  }
  return caught instanceof Error ? caught.message : "Unable to load workload plan";
}

export function StudentWorkloadPlanner({ moduleId, compact = false }: StudentWorkloadPlannerProps) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [availability, setAvailability] = useState<StudentAvailabilityRead | null>(null);
  const [plan, setPlan] = useState<WorkloadPlanRead | null>(null);
  const [studyDays, setStudyDays] = useState<string[]>([]);
  const [preferredWindow, setPreferredWindow] = useState("evening");
  const [maxMinutes, setMaxMinutes] = useState(90);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const syncAvailability = useCallback((next: StudentAvailabilityRead) => {
    setAvailability(next);
    setStudyDays(next.studyDays);
    setPreferredWindow(next.preferredWindow);
    setMaxMinutes(next.maxStudyMinutesPerDay);
  }, []);

  const load = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    try {
      const nextAvailability = await api.analytics.getStudentWorkloadAvailability(moduleId);
      syncAvailability(nextAvailability);
      try {
        setPlan(await api.analytics.getStudentWorkloadPlan(moduleId));
      } catch (caught) {
        if (isMissingPlan(caught)) {
          setPlan(null);
        } else {
          throw caught;
        }
      }
      setLoadState("ready");
    } catch (caught) {
      setError(message(caught));
      setLoadState("error");
    }
  }, [moduleId, syncAvailability]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedDays = useMemo(() => new Set(studyDays), [studyDays]);
  const hasTightItems = plan?.items.some((item) => item.tight) ?? false;

  function toggleDay(day: string) {
    setStudyDays((current) => {
      if (current.includes(day)) {
        return current.filter((item) => item !== day);
      }
      return [...current, day];
    });
  }

  async function saveAvailability() {
    setIsSaving(true);
    setStatusText(null);
    setError(null);
    try {
      const next = await api.analytics.updateStudentWorkloadAvailability(moduleId, {
        studyDays,
        preferredWindow,
        maxStudyMinutesPerDay: maxMinutes,
      });
      syncAvailability(next);
      setStatusText("Availability saved");
    } catch (caught) {
      setError(message(caught));
    } finally {
      setIsSaving(false);
    }
  }

  async function generatePlan() {
    setIsGenerating(true);
    setStatusText(null);
    setError(null);
    try {
      const nextAvailability = await api.analytics.updateStudentWorkloadAvailability(moduleId, {
        studyDays,
        preferredWindow,
        maxStudyMinutesPerDay: maxMinutes,
      });
      syncAvailability(nextAvailability);
      setPlan(await api.analytics.generateStudentWorkloadPlan(moduleId));
      setStatusText("Plan updated");
    } catch (caught) {
      setError(message(caught));
    } finally {
      setIsGenerating(false);
    }
  }

  async function downloadCalendar() {
    if (!plan) return;
    setIsDownloading(true);
    setStatusText(null);
    setError(null);
    try {
      const download = await api.analytics.downloadWorkloadPlanCalendar(plan.id);
      const url = window.URL.createObjectURL(download.blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = download.fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(url), 0);
      setStatusText("Calendar downloaded");
    } catch (caught) {
      setError(message(caught));
    } finally {
      setIsDownloading(false);
    }
  }

  if (loadState === "loading") {
    return (
      <section aria-busy="true" aria-label="Study plan" className="rounded-lg border border-border bg-surface-raised p-4">
        <h2 className="m-0 font-display text-base leading-snug text-text">Loading study plan</h2>
      </section>
    );
  }

  if (loadState === "error") {
    return (
      <section aria-label="Study plan" role="alert" className="rounded-lg border border-danger p-4 text-danger-text">
        <h2 className="m-0 font-display text-base leading-snug">Unable to load study plan</h2>
        <p className="m-0 mt-2 text-sm">{error}</p>
      </section>
    );
  }

  return (
    <section
      aria-labelledby="student-workload-title"
      className="grid gap-4 rounded-lg border border-border bg-surface-raised p-4"
      data-testid="student-workload-planner"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="m-0 mb-1 text-xs font-medium uppercase text-text-muted">Study plan</p>
          <h2 id="student-workload-title" className="m-0 font-display text-lg leading-snug text-text">
            This week and beyond
          </h2>
        </div>
        {plan ? (
          <Badge tone={hasTightItems ? "warning" : "success"} data-testid="workload-plan-state">
            {hasTightItems ? "Tight" : "Planned"}
          </Badge>
        ) : null}
      </header>

      <form
        className={compact ? "grid gap-3" : "grid gap-3 md:grid-cols-[1.3fr_1fr]"}
        data-testid="workload-availability-form"
        onSubmit={(event) => {
          event.preventDefault();
          void generatePlan();
        }}
      >
        <fieldset className="m-0 grid gap-2 rounded-md border border-border p-3">
          <legend className="px-1 text-sm font-medium text-text">Study days</legend>
          <div className="flex flex-wrap gap-2">
            {DAY_OPTIONS.map(([value, label]) => (
              <label
                key={value}
                className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm text-text"
              >
                <input
                  checked={selectedDays.has(value)}
                  data-testid={`workload-day-${value}`}
                  onChange={() => toggleDay(value)}
                  type="checkbox"
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid gap-3">
          <label className="grid gap-1 text-sm font-medium text-text">
            Preferred window
            <select
              className="rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2"
              data-testid="workload-window"
              onChange={(event) => setPreferredWindow(event.target.value)}
              value={preferredWindow}
            >
              {WINDOW_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm font-medium text-text">
            Daily minutes
            <input
              className="rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2"
              data-testid="workload-max-minutes"
              min={15}
              onChange={(event) => setMaxMinutes(Number(event.target.value))}
              type="number"
              value={maxMinutes}
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2 md:col-span-2">
          <Button
            isLoading={isGenerating}
            data-testid="workload-generate"
            type="submit"
          >
            {plan ? "Regenerate plan" : "Generate plan"}
          </Button>
          <Button
            isLoading={isSaving}
            onClick={() => void saveAvailability()}
            type="button"
            variant="secondary"
          >
            Update availability
          </Button>
          {plan ? (
            <Button
              data-testid="workload-export-calendar"
              isLoading={isDownloading}
              onClick={() => void downloadCalendar()}
              type="button"
              variant="secondary"
            >
              Download calendar snapshot
            </Button>
          ) : null}
          {availability ? (
            <span className="text-xs text-text-muted">
              Availability v{availability.availabilityVersion}
            </span>
          ) : null}
          {statusText ? (
            <span aria-live="polite" className="text-xs text-text-muted" data-testid="workload-status">
              {statusText}
            </span>
          ) : null}
        </div>
      </form>

      {error ? (
        <p className="m-0 rounded-md border border-danger bg-danger-muted p-3 text-sm text-danger-text" role="alert">
          {error}
        </p>
      ) : null}

      {plan ? <PlanList plan={plan} /> : <EmptyPlan />}
    </section>
  );
}

function EmptyPlan() {
  return (
    <section
      aria-label="Generated study plan"
      className="rounded-md border border-border bg-surface p-3 text-sm text-text-muted"
      data-testid="workload-plan-empty"
    >
      Set availability and generate a plan to see study blocks here.
    </section>
  );
}

function PlanList({ plan }: { plan: WorkloadPlanRead }) {
  return (
    <section aria-label="Generated study plan" className="grid gap-2" data-testid="workload-plan-list">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
        <span>Plan v{plan.availabilityVersion}</span>
        <span>{plan.items.length} study blocks</span>
      </div>
      <ol className="m-0 grid list-none gap-2 p-0">
        {plan.items.map((item) => (
          <li
            className="grid gap-2 rounded-md border border-border bg-surface p-3"
            data-testid={`workload-plan-item-${item.sortIndex}`}
            key={item.id}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <strong className="block break-words text-sm text-text">{item.label}</strong>
                <span className="text-xs text-text-muted">
                  {timeLabel(item)} · {item.estimateMinutes} min · {reasonLabel(item.reason)}
                </span>
              </div>
              {item.tight ? (
                <Badge tone="warning" data-testid={`workload-tight-${item.sortIndex}`}>
                  Tight
                </Badge>
              ) : null}
            </div>
            {item.tightMessage ? (
              <p className="m-0 text-sm leading-normal text-warning-text">
                {item.tightMessage}
              </p>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

function timeLabel(item: { scheduledDate: string | null; scheduledStartAt: string | null; scheduledEndAt: string | null; window: string | null }) {
  if (!item.scheduledDate || !item.scheduledStartAt || !item.scheduledEndAt) {
    return "Needs another available slot";
  }
  const start = new Date(item.scheduledStartAt);
  const end = new Date(item.scheduledEndAt);
  return `${item.scheduledDate} · ${windowLabel(item.window)} · ${formatTime(start)}-${formatTime(end)}`;
}

function windowLabel(window: string | null): string {
  if (window === "morning") return "Morning";
  if (window === "afternoon") return "Afternoon";
  if (window === "evening") return "Evening";
  return "Window";
}

function reasonLabel(reason: string): string {
  return reason === "deadline" ? "Deadline" : "Gap";
}

function formatTime(value: Date): string {
  return value.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
