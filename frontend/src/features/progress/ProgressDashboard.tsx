"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  BenchmarkRead,
  ForecastRead,
  ProgressDashboardRead,
  ProgressModuleDetail,
  ProgressModuleSummary,
  TopicMasteryRead,
  TrendPointRead,
} from "../../lib/api";
import { api } from "../../lib/api/wrapper";

type LoadState = "loading" | "ready" | "error";

function pct(value: string | null | undefined): string {
  if (value === null || value === undefined) return "Not available";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "Not available";
  return `${Math.round(parsed)}%`;
}

function points(value: string | null | undefined): string {
  if (value === null || value === undefined) return "Not available";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "Not available";
  return String(Math.round(parsed));
}

function stateIcon(state: string): string {
  if (state === "impossible") return "X";
  if (state === "requires_high_score" || state === "at_risk") return "!";
  if (state === "final_no_remaining") return "=";
  return "OK";
}

function stateTone(state: string): React.CSSProperties {
  if (state === "impossible") return styles.stateDanger;
  if (state === "requires_high_score" || state === "at_risk") return styles.stateWarning;
  return styles.stateSuccess;
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : "Unable to load progress";
}

export function ProgressDashboard() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [dashboard, setDashboard] = useState<ProgressDashboardRead | null>(null);
  const [selectedModuleId, setSelectedModuleId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ProgressModuleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [targetStatus, setTargetStatus] = useState<string | null>(null);

  const selectedSummary = useMemo(
    () => dashboard?.modules.find((module) => module.moduleId === selectedModuleId) ?? null,
    [dashboard?.modules, selectedModuleId],
  );

  const loadDashboard = useCallback(async () => {
    setLoadState("loading");
    setError(null);
    try {
      const next = await api.progress.getDashboard();
      setDashboard(next);
      const firstModuleId = next.modules[0]?.moduleId ?? null;
      setSelectedModuleId((current) => current ?? firstModuleId);
      setLoadState("ready");
    } catch (caught) {
      setError(errorMessage(caught));
      setLoadState("error");
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (!selectedModuleId) {
      setDetail(null);
      return;
    }
    let active = true;
    setTargetStatus(null);
    void api.progress
      .getModule(selectedModuleId)
      .then((next) => {
        if (active) setDetail(next);
      })
      .catch((caught) => {
        if (active) setError(errorMessage(caught));
      });
    return () => {
      active = false;
    };
  }, [selectedModuleId]);

  async function updateTarget(nextTarget: string) {
    if (!selectedModuleId) return;
    setTargetStatus("Saving");
    try {
      const next = await api.progress.setTargetGrade(selectedModuleId, {
        targetLetterGrade: nextTarget,
      });
      setDetail(next);
      setDashboard((current) => updateDashboardSummary(current, next));
      setTargetStatus("Saved");
    } catch (caught) {
      setTargetStatus(errorMessage(caught));
    }
  }

  if (loadState === "loading") {
    return (
      <section aria-busy="true" aria-label="My Progress" style={styles.statePanel}>
        <h1 style={styles.stateTitle}>Loading progress</h1>
      </section>
    );
  }

  if (loadState === "error") {
    return (
      <section aria-label="My Progress" role="alert" style={styles.errorPanel}>
        <h1 style={styles.stateTitle}>Unable to load progress</h1>
        <p style={styles.stateText}>{error}</p>
      </section>
    );
  }

  if (!dashboard || dashboard.modules.length === 0) {
    return (
      <section aria-label="My Progress" style={styles.statePanel}>
        <h1 style={styles.stateTitle}>No progress data</h1>
        <p style={styles.stateText}>Assigned modules with progress data will appear here.</p>
      </section>
    );
  }

  return (
    <section aria-labelledby="progress-title" data-testid="progress-dashboard" style={styles.shell}>
      <header style={styles.header}>
        <div>
          <p style={styles.eyebrow}>Student dashboard</p>
          <h1 id="progress-title" style={styles.title}>
            My Progress
          </h1>
        </div>
        <span style={styles.headerBadge}>{dashboard.modules.length} modules</span>
      </header>

      <div style={styles.layout}>
        <ModuleGrid
          modules={dashboard.modules}
          selectedModuleId={selectedModuleId}
          onSelect={setSelectedModuleId}
        />

        <section aria-label="Selected module progress" style={styles.detailColumn}>
          {detail ? (
            <>
              <ForecastPanel
                detail={detail}
                targetStatus={targetStatus}
                onTargetChange={(target) => void updateTarget(target)}
              />
              <BenchmarkCard benchmark={detail.benchmark} />
              <TrendCard trend={detail.trend} />
              <TopicMasteryCard topics={detail.topics} />
              <section
                aria-label="Gamification"
                data-testid="gamification-placeholder"
                style={styles.card}
              >
                <p style={styles.cardEyebrow}>Next</p>
                <h2 style={styles.cardTitle}>Gamification coming soon</h2>
                <p style={styles.stateText}>
                  Streaks and badges will appear here without changing this dashboard layout.
                </p>
              </section>
            </>
          ) : (
            <section aria-busy="true" style={styles.card}>
              <h2 style={styles.cardTitle}>
                Loading {selectedSummary?.title ?? "module"} progress
              </h2>
            </section>
          )}
        </section>
      </div>
    </section>
  );
}

function updateDashboardSummary(
  dashboard: ProgressDashboardRead | null,
  detail: ProgressModuleDetail,
): ProgressDashboardRead | null {
  if (!dashboard) return dashboard;
  return {
    modules: dashboard.modules.map((module) =>
      module.moduleId === detail.moduleId
        ? {
            ...module,
            currentStanding: detail.currentStanding,
            currentLetterGrade: detail.currentLetterGrade,
            targetLetterGrade: detail.targetLetterGrade,
            forecastState: detail.forecast?.state ?? null,
            forecastLabel: detail.forecast?.label ?? null,
          }
        : module,
    ),
  };
}

function ModuleGrid({
  modules,
  selectedModuleId,
  onSelect,
}: {
  modules: ProgressModuleSummary[];
  selectedModuleId: string | null;
  onSelect: (moduleId: string) => void;
}) {
  return (
    <section aria-label="Progress modules" style={styles.moduleGrid}>
      {modules.map((module) => {
        const selected = module.moduleId === selectedModuleId;
        return (
          <button
            aria-pressed={selected}
            data-testid={`progress-module-card-${module.moduleId}`}
            key={module.moduleId}
            onClick={() => onSelect(module.moduleId)}
            style={{
              ...styles.moduleCard,
              ...(selected ? styles.moduleCardSelected : undefined),
            }}
            type="button"
          >
            <span style={styles.moduleTitle}>{module.title}</span>
            <span style={styles.moduleMetric}>
              Standing {points(module.currentStanding)} · {module.currentLetterGrade ?? "No grade"}
            </span>
            <span style={styles.moduleMetric}>
              Target {module.targetLetterGrade ?? "Unset"} · {module.forecastLabel ?? "No forecast"}
            </span>
            {module.latestWeekNumber ? (
              <span style={styles.moduleMetric}>
                Week {module.latestWeekNumber}: {points(module.latestStandingPoints)}
              </span>
            ) : null}
          </button>
        );
      })}
    </section>
  );
}

function ForecastPanel({
  detail,
  targetStatus,
  onTargetChange,
}: {
  detail: ProgressModuleDetail;
  targetStatus: string | null;
  onTargetChange: (target: string) => void;
}) {
  const forecast = detail.forecast;
  return (
    <section aria-label="Grade forecast" data-testid="forecast-panel" style={styles.card}>
      <div style={styles.cardHeader}>
        <div>
          <p style={styles.cardEyebrow}>Grade forecast</p>
          <h2 style={styles.cardTitle}>{detail.title}</h2>
        </div>
        {forecast ? (
          <span
            data-testid="forecast-state"
            style={{ ...styles.stateBadge, ...stateTone(forecast.state) }}
          >
            <span aria-hidden="true" data-testid="forecast-state-icon" style={styles.stateIcon}>
              {stateIcon(forecast.state)}
            </span>
            {forecast.label}
          </span>
        ) : null}
      </div>

      <label style={styles.fieldLabel}>
        Target grade
        <select
          data-testid="target-grade-select"
          onChange={(event) => onTargetChange(event.target.value)}
          style={styles.select}
          value={detail.targetLetterGrade ?? ""}
        >
          <option disabled value="">
            Choose target
          </option>
          {detail.availableTargetGrades.map((grade) => (
            <option key={grade} value={grade}>
              {grade}
            </option>
          ))}
        </select>
      </label>
      {targetStatus ? (
        <p aria-live="polite" data-testid="target-save-status" style={styles.saveStatus}>
          {targetStatus}
        </p>
      ) : null}

      {forecast ? <ForecastBody forecast={forecast} /> : <NoForecast />}
    </section>
  );
}

function ForecastBody({ forecast }: { forecast: ForecastRead }) {
  if (forecast.state === "impossible") {
    return (
      <div style={styles.forecastBody}>
        <p data-testid="impossible-headline" style={styles.forecastHeadline}>
          Best grade still reachable: {forecast.bestReachableLetterGrade}
        </p>
        <p style={styles.stateText}>
          Even at 100% on all remaining work your maximum is {points(forecast.maxReachable)} —{" "}
          {forecast.targetLetterGrade} ({points(forecast.targetPoints)}) is no longer reachable.
        </p>
        <Calculation forecast={forecast} />
      </div>
    );
  }

  if (forecast.state === "final_no_remaining") {
    return (
      <div style={styles.forecastBody}>
        <p style={styles.forecastHeadline}>
          Final grade: {forecast.finalLetterGrade ?? forecast.currentLetterGrade} · no remaining work
        </p>
        <Calculation forecast={forecast} />
      </div>
    );
  }

  if (forecast.state === "achieved") {
    return (
      <div style={styles.forecastBody}>
        <p style={styles.forecastHeadline}>
          Target secured: {forecast.targetLetterGrade}
        </p>
        <p style={styles.stateText}>
          Your current minimum reachable grade already meets this target.
        </p>
        <Calculation forecast={forecast} />
      </div>
    );
  }

  return (
    <div style={styles.forecastBody}>
      <p style={styles.forecastHeadline}>
        Need {pct(forecast.requiredRemainingAverage)} on remaining work
      </p>
      <p style={styles.stateText}>
        Current standing {points(forecast.earnedSoFar)} · target {forecast.targetLetterGrade} (
        {points(forecast.targetPoints)})
      </p>
      <Calculation forecast={forecast} />
    </div>
  );
}

function Calculation({ forecast }: { forecast: ForecastRead }) {
  return (
    <details style={styles.details}>
      <summary style={styles.summary}>How this is calculated</summary>
      {forecast.requiredRemainingAverage ? (
        <p style={styles.stateText}>
          You have earned {points(forecast.earnedSoFar)} points.{" "}
          {pct(String(Number(forecast.remainingWeight) * 100))} of the module remains. To reach{" "}
          {forecast.targetLetterGrade} ({points(forecast.targetPoints)}) you need (
          {points(forecast.targetPoints)} - {points(forecast.earnedSoFar)}) /{" "}
          {pct(String(Number(forecast.remainingWeight) * 100))} ={" "}
          {pct(forecast.requiredRemainingAverage)} on remaining work.
        </p>
      ) : (
        <p style={styles.stateText}>
          No remaining-work requirement is shown because there is no remaining graded work.
        </p>
      )}
    </details>
  );
}

function NoForecast() {
  return (
    <div style={styles.forecastBody}>
      <p style={styles.forecastHeadline}>No target selected</p>
      <p style={styles.stateText}>Choose a target grade to calculate a forecast.</p>
    </div>
  );
}

function BenchmarkCard({ benchmark }: { benchmark: BenchmarkRead | null }) {
  return (
    <section aria-label="Class benchmark" data-testid="benchmark-card" style={styles.card}>
      <p style={styles.cardEyebrow}>Class benchmark</p>
      <h2 style={styles.cardTitle}>Quiz average</h2>
      {benchmark?.suppressed ? (
        <p style={styles.stateText}>
          Hidden until at least {benchmark.suppressionMinCohort} students are in the cohort.
        </p>
      ) : benchmark ? (
        <p style={styles.benchmarkLine}>
          Your quiz average {pct(benchmark.studentAverage)} · Class average {pct(benchmark.classAverage)} ·{" "}
          Cohort {benchmark.cohortSize}
        </p>
      ) : (
        <p style={styles.stateText}>No quiz benchmark yet.</p>
      )}
    </section>
  );
}

function TrendCard({ trend }: { trend: TrendPointRead[] }) {
  return (
    <section aria-label="Progress trend" style={styles.card}>
      <p style={styles.cardEyebrow}>Trend</p>
      <h2 style={styles.cardTitle}>Standing by week</h2>
      <div aria-hidden="true" style={styles.trendBars}>
        {trend.map((point) => (
          <span
            key={point.weekNumber}
            style={{
              ...styles.trendBar,
              height: `${Math.max(8, Number(point.standingPoints))}%`,
            }}
            title={`Week ${point.weekNumber}: ${points(point.standingPoints)}`}
          />
        ))}
      </div>
      <ul data-testid="trend-text-fallback" style={styles.textFallback}>
        {trend.map((point) => (
          <li key={point.weekNumber}>
            Week {point.weekNumber}: {points(point.standingPoints)}
          </li>
        ))}
      </ul>
    </section>
  );
}

function TopicMasteryCard({ topics }: { topics: TopicMasteryRead[] }) {
  return (
    <section aria-label="Topic mastery" style={styles.card}>
      <p style={styles.cardEyebrow}>Topic mastery</p>
      <h2 style={styles.cardTitle}>Lecture and lab topics</h2>
      <div style={styles.topicList}>
        {topics.map((topic) => (
          <div data-testid="mastery-row" key={topic.sectionId} style={styles.topicRow}>
            <div>
              <p style={styles.topicTitle}>{topic.title}</p>
              <p style={styles.topicMeta}>
                {topic.sectionType} · {topic.statusLabel.replaceAll("_", " ")}
              </p>
            </div>
            <strong>{pct(topic.masteryPercentage)}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

const styles = {
  shell: {
    display: "grid",
    gap: 24,
  },
  header: {
    alignItems: "flex-start",
    display: "flex",
    gap: 16,
    justifyContent: "space-between",
  },
  eyebrow: {
    color: "var(--color-text-muted)",
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: 0,
    margin: "0 0 6px",
    textTransform: "uppercase",
  },
  title: {
    color: "var(--color-text)",
    fontSize: 28,
    lineHeight: 1.15,
    margin: 0,
  },
  headerBadge: {
    border: "1px solid var(--color-border)",
    borderRadius: 999,
    color: "var(--color-text-muted)",
    fontSize: 13,
    fontWeight: 700,
    padding: "6px 12px",
  },
  layout: {
    alignItems: "start",
    display: "grid",
    gap: 20,
    gridTemplateColumns: "minmax(220px, 320px) minmax(0, 1fr)",
  },
  moduleGrid: {
    display: "grid",
    gap: 10,
  },
  moduleCard: {
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: 8,
    color: "var(--color-text)",
    cursor: "pointer",
    display: "grid",
    gap: 8,
    padding: 16,
    textAlign: "left",
  },
  moduleCardSelected: {
    borderColor: "var(--color-primary)",
    boxShadow: "inset 3px 0 0 var(--color-primary)",
  },
  moduleTitle: {
    fontSize: 16,
    fontWeight: 700,
    lineHeight: 1.3,
  },
  moduleMetric: {
    color: "var(--color-text-muted)",
    fontSize: 13,
    lineHeight: 1.4,
  },
  detailColumn: {
    display: "grid",
    gap: 16,
    minWidth: 0,
  },
  card: {
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: 8,
    color: "var(--color-text)",
    display: "grid",
    gap: 14,
    padding: 20,
  },
  cardHeader: {
    alignItems: "flex-start",
    display: "flex",
    gap: 16,
    justifyContent: "space-between",
  },
  cardEyebrow: {
    color: "var(--color-text-muted)",
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: 0,
    margin: "0 0 4px",
    textTransform: "uppercase",
  },
  cardTitle: {
    fontSize: 20,
    lineHeight: 1.25,
    margin: 0,
  },
  stateBadge: {
    alignItems: "center",
    borderRadius: 999,
    display: "inline-flex",
    flex: "0 0 auto",
    fontSize: 13,
    fontWeight: 700,
    gap: 6,
    padding: "5px 10px",
  },
  stateIcon: {
    fontSize: 11,
  },
  stateSuccess: {
    background: "var(--color-success-surface)",
    color: "var(--color-success-text)",
  },
  stateWarning: {
    background: "var(--color-warning-surface)",
    color: "var(--color-warning-text)",
  },
  stateDanger: {
    background: "var(--color-danger-surface)",
    color: "var(--color-danger-text)",
  },
  fieldLabel: {
    color: "var(--color-text)",
    display: "grid",
    fontSize: 13,
    fontWeight: 700,
    gap: 6,
    maxWidth: 220,
  },
  select: {
    border: "1px solid var(--color-border-strong)",
    borderRadius: 8,
    color: "var(--color-text)",
    fontSize: 15,
    padding: "8px 10px",
  },
  saveStatus: {
    color: "var(--color-text-muted)",
    fontSize: 13,
    margin: 0,
  },
  forecastBody: {
    borderTop: "1px solid var(--color-border)",
    display: "grid",
    gap: 10,
    paddingTop: 14,
  },
  forecastHeadline: {
    fontSize: 22,
    fontWeight: 700,
    lineHeight: 1.25,
    margin: 0,
  },
  details: {
    borderTop: "1px solid var(--color-border)",
    paddingTop: 10,
  },
  summary: {
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 700,
  },
  benchmarkLine: {
    color: "var(--color-text)",
    fontSize: 16,
    lineHeight: 1.45,
    margin: 0,
  },
  trendBars: {
    alignItems: "end",
    borderBottom: "1px solid var(--color-border)",
    display: "flex",
    gap: 8,
    height: 120,
    paddingTop: 12,
  },
  trendBar: {
    background: "var(--color-primary)",
    borderRadius: "6px 6px 0 0",
    display: "block",
    minHeight: 8,
    width: 28,
  },
  textFallback: {
    color: "var(--color-text-muted)",
    fontSize: 13,
    lineHeight: 1.5,
    margin: 0,
    paddingLeft: 18,
  },
  topicList: {
    display: "grid",
    gap: 8,
  },
  topicRow: {
    alignItems: "center",
    borderTop: "1px solid var(--color-border)",
    display: "flex",
    gap: 12,
    justifyContent: "space-between",
    paddingTop: 10,
  },
  topicTitle: {
    fontSize: 15,
    fontWeight: 700,
    margin: 0,
  },
  topicMeta: {
    color: "var(--color-text-muted)",
    fontSize: 13,
    margin: "4px 0 0",
    textTransform: "capitalize",
  },
  statePanel: {
    border: "1px solid var(--color-border)",
    borderRadius: 8,
    padding: 24,
  },
  errorPanel: {
    border: "1px solid var(--color-danger)",
    borderRadius: 8,
    color: "var(--color-danger-text)",
    padding: 24,
  },
  stateTitle: {
    fontSize: 18,
    lineHeight: 1.35,
    margin: 0,
  },
  stateText: {
    color: "var(--color-text-muted)",
    fontSize: 14,
    lineHeight: 1.5,
    margin: 0,
  },
} satisfies Record<string, React.CSSProperties>;
