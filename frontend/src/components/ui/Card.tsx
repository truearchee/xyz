import type { ReactNode } from "react";

import { cn } from "./cn";

export const cardBase = "rounded-lg border border-border bg-surface-raised shadow-sm";

// Presentational static container — no directive (usable in Server Components). The clickable variant
// is InteractiveCard (a real focusable control), kept in its own client module.
export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn(cardBase, "p-4", className)}>{children}</div>;
}
