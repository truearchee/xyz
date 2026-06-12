import { cn } from "./cn";

// Internal helper — content-region loading placeholder (§4.3 loading convention: skeletons for
// content, inline spinner for button-level actions). Decorative; reduced-motion disables the pulse.
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("motion-safe:animate-pulse rounded-md bg-surface-muted", className)}
    />
  );
}
