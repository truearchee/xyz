import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "./cn";
import { badgeBase, badgeTones, type BadgeTone } from "./variants";

// Presentational. Status is carried by the TEXT label (children), never color alone (§4.2 / the
// quiz-risk a11y rule). Tonal tokens are AA-safe at body size (design-plan validated table).
export function Badge({
  tone = "neutral",
  className,
  children,
  ...rest
}: {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
} & HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn(badgeBase, badgeTones[tone], className)} {...rest}>{children}</span>;
}
