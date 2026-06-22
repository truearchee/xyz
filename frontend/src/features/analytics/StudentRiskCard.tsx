"use client";

import { useEffect, useState } from "react";

import type { StudentRecommendationRead, StudentRiskRead } from "../../lib/api";
import { api } from "../../lib/api/wrapper";
import { StudentRecommendationNudge } from "./StudentRecommendationNudge";

type StudentRiskCardProps = {
  moduleId: string;
};

type LoadState = "loading" | "ready" | "error";

export function StudentRiskCard({ moduleId }: StudentRiskCardProps) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [risk, setRisk] = useState<StudentRiskRead | null>(null);
  const [recommendation, setRecommendation] = useState<StudentRecommendationRead | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoadState("loading");
    setRisk(null);
    setRecommendation(null);
    void Promise.all([
      api.analytics.getStudentRisk(moduleId),
      api.analytics.getStudentModuleRecommendations(moduleId),
    ])
      .then(([nextRisk, nextRecommendations]) => {
        if (!mounted) return;
        setRisk(nextRisk);
        setRecommendation(nextRecommendations.recommendations[0] ?? null);
        setLoadState("ready");
      })
      .catch(() => {
        if (!mounted) return;
        setLoadState("error");
      });
    return () => {
      mounted = false;
    };
  }, [moduleId]);

  if (loadState === "loading") {
    return (
      <section aria-busy="true" aria-label="Where you stand" className="rounded-lg border border-border bg-surface-raised p-4">
        <h2 className="m-0 font-display text-base leading-snug text-text">Where you stand</h2>
      </section>
    );
  }

  if (loadState === "error") {
    return (
      <section aria-label="Where you stand" className="rounded-lg border border-border bg-surface-raised p-4">
        <h2 className="m-0 font-display text-base leading-snug text-text">Where you stand</h2>
        <p className="m-0 mt-2 text-sm leading-normal text-text-muted">This view is not available right now.</p>
      </section>
    );
  }

  const reasons = risk?.riskReasons ?? [];

  return (
    <section aria-label="Where you stand" data-testid="student-risk-card" className="grid gap-3 rounded-lg border border-border bg-surface-raised p-4">
      <div>
        <p className="m-0 mb-1 text-xs font-medium uppercase text-text-muted">Personal check-in</p>
        <h2 className="m-0 font-display text-base leading-snug text-text">Where you stand</h2>
      </div>
      {reasons.length === 0 ? (
        <p className="m-0 text-sm leading-normal text-text-muted">
          Your recent activity looks steady for this module.
        </p>
      ) : recommendation ? (
        <StudentRecommendationNudge
          recommendation={recommendation}
          onDismiss={() => setRecommendation(null)}
        />
      ) : (
        <ul className="m-0 grid list-none gap-2 p-0">
          {reasons.map((reason) => (
            <li
              data-testid={`student-risk-reason-${reason.code}`}
              key={reason.code}
              className="rounded-md border border-border bg-surface p-3 text-sm leading-normal text-text"
            >
              {reason.studentText}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
