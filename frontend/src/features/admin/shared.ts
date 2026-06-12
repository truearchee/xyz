import { ApiError } from "../../lib/api";

export function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function errorMessage(caught: unknown): string {
  if (caught instanceof ApiError) {
    if (typeof caught.body === "object" && caught.body !== null && "detail" in caught.body) {
      const detail = (caught.body as { detail?: unknown }).detail;
      if (typeof detail === "string") {
        return detail;
      }
    }
    return caught.message;
  }

  if (caught instanceof Error) {
    return caught.message;
  }

  return "Unexpected error";
}

// Stage 4.9c: the shared admin styling, migrated from inline CSS objects to semantic-token className
// strings (same shape). Renamed panelStyles -> panelClasses so the compiler flags any dangling importer
// (developer hold #1). errorMessage/slugify are logic and unchanged.
// 4.9e mobile-sanity fix: grid items default to `min-width:auto` and refuse to shrink below their
// content's min-content — so a wide member table or the auto-fit form grid forced the whole panel
// (and the page) past 375px. `min-w-0` lets the panel shrink within the page grid; `[&>*]:min-w-0`
// lets the panel's children shrink, which (a) makes the auto-fit grid see a DEFINITE 343px width so it
// collapses to one column on mobile, and (b) lets the `overflow-x-auto` table wrappers actually clip.
export const panelClasses = {
  panel: "grid min-w-0 gap-4 rounded-lg border border-border bg-surface-raised p-4 shadow-sm [&>*]:min-w-0",
  stack: "grid gap-3 [&>*]:min-w-0",
  grid: "grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]",
  table: "w-full border-collapse",
  th: "border-b border-border px-1.5 py-2 text-left text-xs font-semibold text-text-muted",
  td: "border-b border-border px-1.5 py-2 align-top text-sm text-text",
  label: "grid gap-1 text-xs font-medium text-text",
  // w-full + min-w-0: a <select>'s intrinsic width is its widest <option> (long emails/titles), which
  // would otherwise force the form column past 375px on mobile. w-full fills the column (as it already
  // rendered) and min-w-0 lets it shrink + truncate the displayed option instead of overflowing the page.
  input:
    "w-full min-w-0 rounded-md border border-border-strong px-2.5 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2",
  buttonRow: "flex flex-wrap items-center gap-2",
  alert: "rounded-md border border-danger bg-danger-surface p-2.5 text-sm text-danger-text",
  status: "rounded-md border border-success bg-success-surface p-2.5 text-sm text-success-text",
  button:
    "min-h-[38px] rounded-md border border-primary bg-primary px-3.5 text-sm font-bold text-on-primary hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60",
  buttonSecondary:
    "min-h-[34px] rounded-md border border-border-strong bg-surface px-3 text-sm font-medium text-text hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60",
} as const;
