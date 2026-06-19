import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// Stage 4.9b — the one className combiner. clsx resolves conditionals; tailwind-merge dedupes
// conflicting utilities so a caller's className override actually wins over a variant default.
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
