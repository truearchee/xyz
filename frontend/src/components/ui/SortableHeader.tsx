"use client";

import { cn } from "./cn";

// Sortable column header — a REAL <button> inside a <th scope="col"> (§4.2: "sortable headers are
// buttons"), with aria-sort on the th reflecting the active direction. Client (onSort handler).
type SortDirection = "ascending" | "descending" | "none";

export function SortableHeader({
  label,
  direction = "none",
  onSort,
  className,
}: {
  label: string;
  direction?: SortDirection;
  onSort?: () => void;
  className?: string;
}) {
  const glyph = direction === "ascending" ? "▲" : direction === "descending" ? "▼" : "";
  return (
    <th scope="col" aria-sort={direction} className={className}>
      <button
        type="button"
        onClick={onSort}
        className={cn(
          "inline-flex items-center gap-1 font-semibold text-text-muted hover:text-text",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2",
        )}
      >
        {label}
        {glyph ? <span aria-hidden="true">{glyph}</span> : null}
      </button>
    </th>
  );
}
