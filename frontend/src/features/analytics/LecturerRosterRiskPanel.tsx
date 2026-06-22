"use client";

import { useEffect, useMemo, useState } from "react";

import type {
  LecturerRosterRiskRead,
  LecturerRosterRiskRow,
  LecturerStudentRecommendationsRead,
  RecommendationRead,
  RiskReasonRead,
} from "../../lib/api";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { api } from "../../lib/api/wrapper";

type LecturerRosterRiskPanelProps = {
  moduleId: string;
};

type LoadState = "loading" | "ready" | "error";
type Filter = "all" | "needs_support" | "watch" | "on_track";

const FILTER_LABELS: Record<Filter, string> = {
  all: "All",
  needs_support: "Needs support",
  watch: "Watch",
  on_track: "On track",
};

export function LecturerRosterRiskPanel({ moduleId }: LecturerRosterRiskPanelProps) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [risk, setRisk] = useState<LecturerRosterRiskRead | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LecturerStudentRecommendationsRead | null>(null);
  const [detailState, setDetailState] = useState<LoadState>("loading");
  const [copyStatus, setCopyStatus] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoadState("loading");
    void api.analytics
      .getLecturerRosterRisk(moduleId)
      .then((next) => {
        if (!mounted) return;
        setRisk(next);
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

  const rows = useMemo(() => {
    const allRows = risk?.rows ?? [];
    return filter === "all" ? allRows : allRows.filter((row) => row.riskTier === filter);
  }, [filter, risk?.rows]);

  useEffect(() => {
    if (!selectedStudentId) {
      setDetail(null);
      setCopyStatus(null);
      return;
    }
    let mounted = true;
    setDetailState("loading");
    setDetail(null);
    setCopyStatus(null);
    void api.analytics
      .getLecturerStudentRecommendations(moduleId, selectedStudentId)
      .then((next) => {
        if (!mounted) return;
        setDetail(next);
        setDetailState("ready");
      })
      .catch(() => {
        if (!mounted) return;
        setDetailState("error");
      });
    return () => {
      mounted = false;
    };
  }, [moduleId, selectedStudentId]);

  if (loadState === "loading") {
    return (
      <section aria-busy="true" aria-label="Roster risk" className="rounded-lg border border-border bg-surface-raised p-4">
        <h2 className="m-0 font-display text-base leading-snug text-text">Loading roster risk</h2>
      </section>
    );
  }

  if (loadState === "error") {
    return (
      <section aria-label="Roster risk" role="alert" className="rounded-lg border border-danger p-4 text-danger-text">
        <h2 className="m-0 font-display text-base leading-snug">Unable to load roster risk</h2>
      </section>
    );
  }

  return (
    <section aria-labelledby="roster-risk-title" data-testid="lecturer-roster-risk" className="grid gap-3.5 rounded-lg border border-border bg-surface-raised p-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="m-0 mb-1 text-xs font-medium uppercase text-text-muted">Analytics</p>
          <h2 id="roster-risk-title" className="m-0 font-display text-lg leading-snug text-text">Roster risk</h2>
        </div>
        <Badge tone={risk?.needsSupportCount ? "warning" : "success"} data-testid="needs-support-count">
          Needs support: {risk?.needsSupportCount ?? 0}
        </Badge>
      </header>

      <label className="grid max-w-xs gap-1 text-sm font-medium text-text">
        Tier filter
        <select
          value={filter}
          onChange={(event) => setFilter(event.target.value as Filter)}
          className="rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2"
        >
          {(Object.keys(FILTER_LABELS) as Filter[]).map((key) => (
            <option key={key} value={key}>{FILTER_LABELS[key]}</option>
          ))}
        </select>
      </label>

      {rows.length === 0 ? (
        <p className="m-0 text-sm leading-normal text-text-muted">No students match this filter.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-left text-sm text-text">
            <thead>
              <tr className="border-b border-border text-xs uppercase text-text-muted">
                <th className="py-2 pr-4 font-medium">Student</th>
                <th className="py-2 pr-4 font-medium">Tier</th>
                <th className="py-2 pr-4 font-medium">Reasons</th>
                <th className="py-2 pr-0 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <RosterRiskRow key={row.studentId} row={row} onOpen={() => setSelectedStudentId(row.studentId)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <RecommendationModal
        detail={detail}
        isOpen={selectedStudentId !== null}
        loadState={detailState}
        copyStatus={copyStatus}
        onCopyStatus={setCopyStatus}
        onClose={() => setSelectedStudentId(null)}
        onRefresh={() => {
          if (selectedStudentId) {
            setDetailState("loading");
            void api.analytics.getLecturerStudentRecommendations(moduleId, selectedStudentId).then((next) => {
              setDetail(next);
              setDetailState("ready");
            });
          }
        }}
      />
    </section>
  );
}

function RosterRiskRow({ row, onOpen }: { row: LecturerRosterRiskRow; onOpen: () => void }) {
  return (
    <tr data-testid={`lecturer-risk-row-${row.studentId}`} className="border-b border-border align-top last:border-b-0">
      <td className="py-3 pr-4">
        <strong className="block font-semibold">{row.studentName}</strong>
        <span className="text-xs text-text-muted">{row.studentEmail}</span>
      </td>
      <td className="py-3 pr-4">
        <Badge tone={toneForTier(row.riskTier)}>{row.riskLabel}</Badge>
      </td>
      <td className="py-3 pr-4">
        {row.riskReasons.length === 0 ? (
          <span className="text-text-muted">No current risk reasons</span>
        ) : (
          <ul className="m-0 grid list-none gap-2 p-0">
            {row.riskReasons.map((reason) => (
              <RiskReasonItem key={`${row.studentId}-${reason.code}-${reason.metricKeys.join("-")}`} reason={reason} />
            ))}
          </ul>
        )}
      </td>
      <td className="py-3 pr-0 text-right">
        <Button variant="secondary" size="sm" onClick={onOpen}>
          Review
        </Button>
      </td>
    </tr>
  );
}

function RecommendationModal({
  copyStatus,
  detail,
  isOpen,
  loadState,
  onClose,
  onCopyStatus,
  onRefresh,
}: {
  copyStatus: string | null;
  detail: LecturerStudentRecommendationsRead | null;
  isOpen: boolean;
  loadState: LoadState;
  onClose: () => void;
  onCopyStatus: (status: string | null) => void;
  onRefresh: () => void;
}) {
  const recommendation = detail?.recommendations[0] ?? null;

  async function copyDraft() {
    if (!recommendation) return;
    await navigator.clipboard.writeText(recommendation.lecturerDraftText);
    onCopyStatus("Copied");
  }

  async function markActed() {
    if (!recommendation) return;
    await api.analytics.markLecturerRecommendationActed(recommendation.id);
    onRefresh();
  }

  async function dismiss() {
    if (!recommendation) return;
    await api.analytics.dismissLecturerRecommendation(recommendation.id);
    onRefresh();
  }

  return (
    <Modal
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={detail ? `${detail.studentName} recommendation` : "Recommendation"}
      footer={
        recommendation ? (
          <>
            <Button variant="secondary" onClick={() => void copyDraft()}>
              Copy draft
            </Button>
            <Button variant="secondary" onClick={() => void markActed()}>
              Mark acted
            </Button>
            <Button variant="secondary" onClick={() => void dismiss()}>
              Dismiss
            </Button>
          </>
        ) : null
      }
    >
      {loadState === "loading" ? (
        <p className="m-0 text-sm text-text-muted">Loading recommendation</p>
      ) : loadState === "error" ? (
        <p className="m-0 text-sm text-danger-text">Unable to load recommendation.</p>
      ) : !recommendation ? (
        <p className="m-0 text-sm text-text-muted">No current recommendation for this student.</p>
      ) : (
        <div className="grid gap-4" data-testid="lecturer-recommendation-modal">
          <section className="grid gap-2">
            <h3 className="m-0 font-display text-sm font-semibold text-text">Reasons</h3>
            <ul className="m-0 grid list-none gap-2 p-0">
              {detail?.riskReasons.map((reason) => (
                <RiskReasonItem key={`${reason.code}-${reason.metricKeys.join("-")}`} reason={reason} />
              ))}
            </ul>
          </section>
          <RecommendationDraft recommendation={recommendation} />
          <section className="grid gap-2">
            <h3 className="m-0 font-display text-sm font-semibold text-text">Student preview</h3>
            <p className="m-0 rounded-md border border-border bg-surface p-3 text-sm leading-normal text-text">
              {recommendation.studentNudgeText}
            </p>
          </section>
          {copyStatus ? <p className="m-0 text-xs text-text-muted">{copyStatus}</p> : null}
        </div>
      )}
    </Modal>
  );
}

function RecommendationDraft({ recommendation }: { recommendation: RecommendationRead }) {
  return (
    <section className="grid gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="m-0 font-display text-sm font-semibold text-text">Draft</h3>
        <Badge tone={recommendation.lecturerDraftSource === "ai" ? "success" : "neutral"}>
          {recommendation.lecturerDraftSource === "ai" ? "AI phrasing" : "Template"}
        </Badge>
      </div>
      <p className="m-0 rounded-md border border-border bg-surface p-3 text-sm leading-normal text-text">
        {recommendation.lecturerDraftText}
      </p>
    </section>
  );
}

function RiskReasonItem({ reason }: { reason: RiskReasonRead }) {
  return (
    <li data-testid={`lecturer-risk-reason-${reason.code}`} className="grid gap-1">
      <span>{reason.lecturerText}</span>
      <span className="text-xs text-text-muted">
        {reason.metricKeys.map((key) => `${key}: ${formatMetric(reason.supportingMetrics[key])}`).join(" · ")}
      </span>
    </li>
  );
}

function toneForTier(tier: string): "neutral" | "warning" | "success" {
  if (tier === "needs_support") return "warning";
  if (tier === "watch") return "neutral";
  return "success";
}

function formatMetric(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  return String(value);
}
