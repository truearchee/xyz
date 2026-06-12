import type { ReactNode } from "react";

import { cn } from "./cn";

// Presentational. An empty/failed region is an invitation to act: a heading + one clear action
// (§4.2). Also the §4.3 "failed load → Empty State with a retry action" primitive. headingLevel lets
// route-level surfaces keep their <h1> (so gate selectors that match a heading by name are preserved).
type EmptyStateProps = {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  headingLevel?: 1 | 2 | 3;
  className?: string;
};

export function EmptyState({
  title,
  description,
  action,
  icon,
  headingLevel = 2,
  className,
}: EmptyStateProps) {
  const Heading = `h${headingLevel}` as "h1" | "h2" | "h3";
  return (
    <div className={cn("flex flex-col items-center gap-3 px-4 py-10 text-center", className)}>
      {icon ? (
        <div className="text-text-muted" aria-hidden="true">
          {icon}
        </div>
      ) : null}
      <Heading className="font-display text-lg font-semibold text-text">{title}</Heading>
      {description ? <p className="max-w-prose text-sm text-text-muted">{description}</p> : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}
