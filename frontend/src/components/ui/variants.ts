// Stage 4.9b — variant → COMPLETE LITERAL class strings (§4.2 purge footgun: never construct
// `bg-${variant}` — the v4 scanner only sees literals; a constructed class vanishes in `next build`).
// Colors are semantic tokens only (ADR-045); no raw hex, no --palette-* (developer hold #2).

// Shared focus treatment (design-plan Part 4 — visible focus ring on every interactive element).
export const focusRing =
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface";

// ---- Button ----------------------------------------------------------------
export const buttonBase =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 " +
  focusRing;

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";
export const buttonVariants: Record<ButtonVariant, string> = {
  primary: "bg-primary text-on-primary hover:bg-primary-hover",
  secondary: "border border-border bg-surface text-text hover:bg-surface-muted",
  ghost: "bg-transparent text-text hover:bg-surface-muted",
  destructive: "bg-danger text-on-danger hover:bg-danger-hover",
};

export type ButtonSize = "sm" | "md" | "lg";
export const buttonSizes: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-11 px-5 text-base",
};

// ---- Badge -----------------------------------------------------------------
// Tonal pairs (dark -text on light -surface) so status is AA-safe at body size AND never color-only
// (the text label always carries the meaning). Solid white-on-fill is large/UI-only — not used here.
export type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger";
export const badgeBase =
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium";
export const badgeTones: Record<BadgeTone, string> = {
  neutral: "border-border bg-surface-muted text-text-muted",
  info: "border-info bg-info-surface text-info-text",
  success: "border-success bg-success-surface text-success-text",
  warning: "border-warning bg-warning-surface text-warning-text",
  danger: "border-danger bg-danger-surface text-danger-text",
};

// ---- Progress / Step -------------------------------------------------------
// Per-step states. FAILED is mandatory + visually distinct (danger), NEVER rendered as merely
// "not completed" (§4.2 + design-plan 1.4 signature pipeline). Every state also carries a text label.
export type StepState = "pending" | "active" | "completed" | "failed";
export const stepNode: Record<StepState, string> = {
  pending: "border-2 border-border bg-surface text-text-muted",
  active: "border-2 border-primary bg-surface text-primary motion-safe:animate-pulse",
  completed: "border-2 border-primary bg-primary text-on-primary",
  failed: "border-2 border-danger bg-danger text-on-danger",
};
export const stepLabel: Record<StepState, string> = {
  pending: "text-text-muted",
  active: "text-primary font-medium",
  completed: "text-text",
  failed: "text-danger-text font-semibold",
};
