import type { ReactNode } from "react";

import { cn } from "./cn";
import { badgeBase, badgeTones, type BadgeTone } from "./variants";

// Presentational. Status is carried by the TEXT label (children), never color alone (§4.2 / the
// quiz-risk a11y rule). Tonal tokens are AA-safe at body size (design-plan validated table).
export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
}) {
  return <span className={cn(badgeBase, badgeTones[tone], className)}>{children}</span>;
}
