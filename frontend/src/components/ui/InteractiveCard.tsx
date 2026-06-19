"use client";

import type { ReactNode } from "react";

import { cardBase } from "./Card";
import { cn } from "./cn";

// Interactive Card — a REAL control with focus (§4.2: "if clickable, a real control, not a div +
// onClick"). <a> when href is given, else a <button>. Client because of the onClick handler.
export function InteractiveCard({
  href,
  onClick,
  className,
  children,
}: {
  href?: string;
  onClick?: () => void;
  className?: string;
  children: ReactNode;
}) {
  const interactive = cn(
    cardBase,
    "block w-full p-4 text-left transition-colors hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2",
    className,
  );
  if (href) {
    return (
      <a href={href} className={interactive}>
        {children}
      </a>
    );
  }
  return (
    <button type="button" onClick={onClick} className={interactive}>
      {children}
    </button>
  );
}
