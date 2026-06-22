"use client";

import { useEffect, useState } from "react";

import type { StudentRecommendationRead } from "../../lib/api";
import { api } from "../../lib/api/wrapper";
import { StudentRecommendationNudge } from "./StudentRecommendationNudge";

export function StudentRecommendationBanner() {
  const [recommendation, setRecommendation] = useState<StudentRecommendationRead | null>(null);

  useEffect(() => {
    let mounted = true;
    void api.analytics
      .getStudentRecommendationBanner()
      .then((next) => {
        if (!mounted) return;
        setRecommendation(next.recommendation ?? null);
      })
      .catch(() => {
        if (!mounted) return;
        setRecommendation(null);
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (!recommendation) return null;

  return (
    <StudentRecommendationNudge
      recommendation={recommendation}
      variant="banner"
      onDismiss={() => setRecommendation(null)}
    />
  );
}
