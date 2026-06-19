import type { ReactNode } from "react";

// Internal helper — visually hidden but screen-reader-available text (sr-only). Used where a control's
// visible label is an icon and an accessible name is still required.
export function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span className="sr-only">{children}</span>;
}
