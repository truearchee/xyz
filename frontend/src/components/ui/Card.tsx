import type { ReactNode } from "react";

import { cn } from "./cn";

// No resting shadow (design-system §6) — cards separate from the parchment page by the white
// surface-tone step + the hairline border. Soft shadow is reserved for overlays (Modal/Toast).
export const cardBase = "rounded-lg border border-border bg-surface-raised";

// Presentational static container — no directive (usable in Server Components). The clickable variant
// is InteractiveCard (a real focusable control), kept in its own client module.
export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn(cardBase, "p-4", className)}>{children}</div>;
}
