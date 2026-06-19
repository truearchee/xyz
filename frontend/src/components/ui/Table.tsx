import type { ReactNode } from "react";

import { cn } from "./cn";

// Presentational semantic <table> shell (§4.2). Consumers compose native <thead>/<tbody>/<tr>/<th>/<td>;
// the wrapper provides overflow + token styling for descendant cells. Row emphasis uses border + tint
// (NOT color alone): apply `tableRowEmphasis` to the emphasized <tr> (later risk rows).
export const tableRowEmphasis = "border-l-2 border-l-danger bg-danger-surface";

export function Table({ caption, className, children }: { caption?: string; className?: string; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table
        className={cn(
          "w-full border-collapse text-left text-sm",
          "[&_th]:px-3 [&_th]:py-2 [&_th]:font-semibold [&_th]:text-text-muted",
          "[&_td]:border-t [&_td]:border-border [&_td]:px-3 [&_td]:py-2 [&_td]:text-text",
          className,
        )}
      >
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        {children}
      </table>
    </div>
  );
}
