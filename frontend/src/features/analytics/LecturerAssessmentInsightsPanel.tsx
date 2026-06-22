"use client";

import { useEffect, useMemo, useState } from "react";

import type {
  AssessmentQuestionInsightRead,
  LecturerAssessmentInsightsRead,
} from "../../lib/api";
import { Badge } from "../../components/ui/Badge";
import { api } from "../../lib/api/wrapper";

type LecturerAssessmentInsightsPanelProps = {
  moduleId: string;
};

type LoadState = "loading" | "ready" | "error";

export function LecturerAssessmentInsightsPanel({
  moduleId,
}: LecturerAssessmentInsightsPanelProps) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [insights, setInsights] = useState<LecturerAssessmentInsightsRead | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoadState("loading");
    void api.analytics
      .getLecturerAssessmentInsights(moduleId)
      .then((next) => {
        if (!mounted) return;
        setInsights(next);
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

  const mostMissed = useMemo(
    () => insights?.mostMissedQuestions ?? [],
    [insights?.mostMissedQuestions],
  );

  if (loadState === "loading") {
    return (
      <section
        aria-busy="true"
        aria-label="Assessment insights"
        className="rounded-lg border border-border bg-surface-raised p-4"
      >
        <h2 className="m-0 font-display text-base leading-snug text-text">
          Loading assessment insights
        </h2>
      </section>
    );
  }

  if (loadState === "error") {
    return (
      <section
        aria-label="Assessment insights"
        role="alert"
        className="rounded-lg border border-danger p-4 text-danger-text"
      >
        <h2 className="m-0 font-display text-base leading-snug">
          Unable to load assessment insights
        </h2>
      </section>
    );
  }

  return (
    <section
      aria-labelledby="assessment-insights-title"
      data-testid="lecturer-assessment-insights"
      className="grid gap-4 rounded-lg border border-border bg-surface-raised p-4"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="m-0 mb-1 text-xs font-medium uppercase text-text-muted">
            Assessment analysis
          </p>
          <h2
            id="assessment-insights-title"
            className="m-0 font-display text-lg leading-snug text-text"
          >
            Question insights
          </h2>
        </div>
        <Badge tone="neutral" data-testid="assessment-question-count">
          Questions: {insights?.questions.length ?? 0}
        </Badge>
      </header>

      {insights?.latestAgentRun ? (
        <p className="m-0 text-xs leading-normal text-text-muted">
          Latest agent run: {insights.latestAgentRun.status}
        </p>
      ) : null}

      <TopicMastery insights={insights} />
      <MostMissed questions={mostMissed} />
      <QuestionTable questions={insights?.questions ?? []} />
    </section>
  );
}

function TopicMastery({ insights }: { insights: LecturerAssessmentInsightsRead | null }) {
  const topicMastery = insights?.topicMastery;
  if (!topicMastery) return null;

  return (
    <section aria-labelledby="topic-mastery-title" className="grid gap-2">
      <h3
        id="topic-mastery-title"
        className="m-0 font-display text-base leading-snug text-text"
      >
        Topic mastery
      </h3>
      {topicMastery.unmappedMessage ? (
        <p
          className="m-0 rounded-md border border-warning bg-warning-muted p-3 text-sm text-warning-text"
          data-testid="topic-mastery-unavailable"
        >
          {topicMastery.unmappedMessage}
        </p>
      ) : null}
      {!topicMastery.available ? (
        <p
          className="m-0 rounded-md border border-border bg-surface p-3 text-sm text-text-muted"
          data-testid="topic-mastery-unavailable-all"
        >
          {topicMastery.unavailableReason ?? insights?.smallCohortMessage}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-left text-sm text-text">
            <thead>
              <tr className="border-b border-border text-xs uppercase text-text-muted">
                <th className="py-2 pr-4 font-medium">Topic</th>
                <th className="py-2 pr-4 font-medium">Submissions</th>
                <th className="py-2 pr-0 font-medium">Mastery</th>
              </tr>
            </thead>
            <tbody>
              {topicMastery.rows.map((row) => (
                <tr
                  key={row.sourceSectionId}
                  data-testid={`topic-mastery-row-${row.sourceSectionId}`}
                  className="border-b border-border last:border-b-0"
                >
                  <td className="py-2 pr-4">
                    <strong className="block font-semibold">{row.topicTitle}</strong>
                    <span className="text-xs text-text-muted">
                      {row.weekNumber === null ? "Unstamped" : `Week ${row.weekNumber}`}
                    </span>
                  </td>
                  <td className="py-2 pr-4">{row.answerCount}</td>
                  <td className="py-2 pr-0" data-testid={`topic-mastery-percent-${row.sourceSectionId}`}>
                    {row.smallCohort
                      ? row.smallCohortMessage
                      : formatPercent(row.masteryPercent)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function MostMissed({ questions }: { questions: AssessmentQuestionInsightRead[] }) {
  return (
    <section aria-labelledby="most-missed-title" className="grid gap-2">
      <h3
        id="most-missed-title"
        className="m-0 font-display text-base leading-snug text-text"
      >
        Most missed
      </h3>
      {questions.length === 0 ? (
        <p className="m-0 text-sm text-text-muted">
          Not enough submissions for an aggregate insight
        </p>
      ) : (
        <ol className="m-0 grid list-decimal gap-2 pl-5 text-sm text-text">
          {questions.map((question) => (
            <li key={question.questionKey} data-testid={`most-missed-${question.questionKey}`}>
              <span className="font-medium">{question.questionText}</span>
              <span className="text-text-muted">
                {" "}
                · {question.incorrectCount} missed · {formatPercent(question.correctRatePercent)} correct
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function QuestionTable({ questions }: { questions: AssessmentQuestionInsightRead[] }) {
  if (questions.length === 0) {
    return (
      <p className="m-0 text-sm text-text-muted">
        No completed quiz submissions yet.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-collapse text-left text-sm text-text">
        <thead>
          <tr className="border-b border-border text-xs uppercase text-text-muted">
            <th className="py-2 pr-4 font-medium">Question</th>
            <th className="py-2 pr-4 font-medium">Correct rate</th>
            <th className="py-2 pr-4 font-medium">Missed</th>
            <th className="py-2 pr-0 font-medium">Distractors</th>
          </tr>
        </thead>
        <tbody>
          {questions.map((question) => (
            <tr
              key={question.questionKey}
              data-testid={`assessment-question-${question.questionKey}`}
              className="border-b border-border align-top last:border-b-0"
            >
              <td className="py-3 pr-4">
                <strong className="block font-semibold">{question.questionText}</strong>
                <span className="text-xs text-text-muted">
                  {question.answerCount} submissions
                </span>
              </td>
              <td className="py-3 pr-4" data-testid={`assessment-question-rate-${question.questionKey}`}>
                {question.smallCohort
                  ? question.smallCohortMessage
                  : formatPercent(question.correctRatePercent)}
              </td>
              <td className="py-3 pr-4">{question.incorrectCount}</td>
              <td className="py-3 pr-0">
                {question.distractors.length === 0 ? (
                  <span className="text-text-muted">No wrong-option picks</span>
                ) : (
                  <ul className="m-0 grid list-none gap-1 p-0">
                    {question.distractors.map((distractor) => (
                      <li
                        key={distractor.optionKey}
                        data-testid={`assessment-distractor-${question.questionKey}-${distractor.optionKey}`}
                      >
                        {distractor.optionText}: {distractor.selectedCount}
                        {distractor.selectedRatePercent === null
                          ? ""
                          : ` (${formatPercent(distractor.selectedRatePercent)})`}
                      </li>
                    ))}
                  </ul>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatPercent(value: string | null): string {
  if (value === null) return "";
  return `${Number(value).toFixed(2)}%`;
}
