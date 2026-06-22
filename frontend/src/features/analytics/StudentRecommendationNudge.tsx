"use client";

import { useState } from "react";

import type { StudentRecommendationRead } from "../../lib/api";
import { api } from "../../lib/api/wrapper";

type StudentRecommendationNudgeProps = {
  recommendation: StudentRecommendationRead;
  variant?: "card" | "banner";
  onDismiss?: (id: string) => void;
};

export function StudentRecommendationNudge({
  recommendation,
  variant = "card",
  onDismiss,
}: StudentRecommendationNudgeProps) {
  const [isDismissing, setIsDismissing] = useState(false);

  async function dismiss() {
    setIsDismissing(true);
    try {
      await api.analytics.dismissStudentRecommendation(recommendation.id);
      onDismiss?.(recommendation.id);
    } finally {
      setIsDismissing(false);
    }
  }

  return (
    <div
      data-testid={variant === "banner" ? "student-recommendation-banner" : "student-recommendation-nudge"}
      className={
        variant === "banner"
          ? "grid gap-2 rounded-lg border border-border-strong bg-surface-raised p-4"
          : "grid gap-2 rounded-md border border-border bg-surface p-3"
      }
    >
      <p className="m-0 text-sm leading-normal text-text">{recommendation.text}</p>
      <p className="m-0 text-xs leading-normal text-text-muted">{recommendation.nextStep}</p>
      <div className="flex justify-end">
        <button
          type="button"
          disabled={isDismissing}
          onClick={() => void dismiss()}
          className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2"
        >
          Not now
        </button>
      </div>
    </div>
  );
}
