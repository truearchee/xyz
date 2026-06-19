"use client";

import { ApiError } from "../../lib/api";

export type AssistantReadiness = "ready" | "processing" | "unavailable";
export type NonReadyAssistantReadiness = Exclude<AssistantReadiness, "ready">;

export function assistantReadinessFromError(caught: unknown): NonReadyAssistantReadiness | null {
  if (!(caught instanceof ApiError) || caught.status !== 409) return null;
  const detail = caught.body?.detail;
  if (detail?.code !== "assistant_not_ready") return null;
  return detail.state === "processing" ? "processing" : "unavailable";
}
