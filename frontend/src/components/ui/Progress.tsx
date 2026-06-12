import { cn } from "./cn";
import { stepLabel, stepNode, type StepState } from "./variants";

// Presentational. Two forms: a linear bar and the stepped PIPELINE (design-plan 1.4 signature element).

// ---- Linear -----------------------------------------------------------------
export function LinearProgress({
  value,
  label,
  className,
}: {
  value: number;
  label: string;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex justify-between text-xs text-text-muted">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-surface-muted"
        role="progressbar"
        aria-label={label}
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-[var(--motion-duration-base)]"
          // Dynamic runtime value (continuous %), not a design hardcode — the sanctioned inline-style
          // use (the §8 check:inline-styles gate targets un-migrated feature surfaces, not this).
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ---- Stepped pipeline -------------------------------------------------------
// The signature element. Per-step state incl. the MANDATORY, visually-distinct FAILED state — never
// rendered as merely "not completed". Status is ALWAYS carried by visible text (STEP_STATE_TEXT), not
// color alone; the node glyph is decorative (aria-hidden).
const STEP_STATE_TEXT: Record<StepState, string> = {
  pending: "Pending",
  active: "In progress",
  completed: "Done",
  failed: "Failed",
};

export type PipelineStep = { label: string; state: StepState };

export function StepProgress({
  steps,
  orientation = "horizontal",
  className,
}: {
  steps: PipelineStep[];
  orientation?: "horizontal" | "vertical";
  className?: string;
}) {
  return (
    <ol
      className={cn(
        "flex gap-4",
        orientation === "vertical" ? "flex-col" : "flex-row flex-wrap items-start",
        className,
      )}
    >
      {steps.map((step, i) => (
        <li key={`${step.label}-${i}`} className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className={cn(
              "flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
              stepNode[step.state],
            )}
          >
            {step.state === "completed" ? "✓" : step.state === "failed" ? "✕" : i + 1}
          </span>
          <span className="flex flex-col leading-tight">
            <span className={cn("text-sm", stepLabel[step.state])}>{step.label}</span>
            <span
              className={cn(
                "text-xs",
                step.state === "failed" ? "text-danger-text font-semibold" : "text-text-muted",
              )}
            >
              {STEP_STATE_TEXT[step.state]}
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}
