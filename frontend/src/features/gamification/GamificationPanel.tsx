"use client";

import { useEffect, useState } from "react";

import { Badge, Card, EmptyState, LinearProgress, Skeleton, cn } from "../../components/ui";
import type {
  EarnedBadgeRead,
  GamificationRead,
  LockedBadgeRead,
  ProgressItemRead,
} from "../../lib/api";
import { api } from "../../lib/api/wrapper";

type LoadState = "loading" | "ready" | "error";

// Decorative glyphs only (aria-hidden) — the badge TITLE carries meaning, never the icon (a11y §4.2).
const BADGE_GLYPHS: Record<string, string> = {
  flame: "🔥",
  check: "✅",
  book: "📖",
  cards: "🃏",
  bookmark: "🔖",
  sunrise: "🌅",
  star: "⭐",
  trophy: "🏆",
  medal: "🏅",
  stack: "📚",
};

// streakStatus → a plain-text line (status is conveyed by TEXT, never colour/icon alone).
const STATUS_COPY: Record<string, string> = {
  active: "You're covered for today.",
  needs_activity_today: "Do any learning activity today to keep your streak going.",
  no_scheduled_day: "No class scheduled today — your streak is safe.",
  broken:
    "Your previous streak ended after a missed class day. Do an activity today to start a new one.",
};

function glyph(icon: string): string {
  return BADGE_GLYPHS[icon] ?? "🏷️";
}

function pct(current: number, target: number): number {
  return target > 0 ? Math.round((current / target) * 100) : 0;
}

function errorMessage(caught: unknown): string {
  return caught instanceof Error ? caught.message : "Unable to load gamification";
}

export function GamificationPanel() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [data, setData] = useState<GamificationRead | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoadState("loading");
    api.gamification
      .get()
      .then((next) => {
        if (active) {
          setData(next);
          setLoadState("ready");
        }
      })
      .catch((caught) => {
        if (active) {
          setError(errorMessage(caught));
          setLoadState("error");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  // The section wrapper renders synchronously so the My Progress placeholder slot is always present.
  return (
    <section
      aria-label="Gamification"
      data-testid="gamification-placeholder"
      className="flex flex-col gap-4 rounded-lg border border-border bg-surface-raised p-4"
    >
      <h2 className="text-xl font-semibold text-text">Streaks &amp; badges</h2>

      {loadState === "loading" && (
        <div className="flex flex-col gap-3" aria-busy="true">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      )}

      {loadState === "error" && (
        <p role="alert" className="text-sm text-danger-text">
          {error}
        </p>
      )}

      {loadState === "ready" && data && <GamificationBody data={data} />}
    </section>
  );
}

function GamificationBody({ data }: { data: GamificationRead }) {
  return (
    <div data-testid="gamification-panel" className="flex flex-col gap-5">
      <StreakRow data={data} />
      <ProgressList items={data.progressItems} />
      <BadgeGrid earned={data.earnedBadges} locked={data.lockedBadges} />
    </div>
  );
}

function StreakRow({ data }: { data: GamificationRead }) {
  const broken = data.streakStatus === "broken";
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-4">
        <span aria-hidden="true" className="text-3xl">
          🔥
        </span>
        <div>
          <p
            data-testid="streak-current"
            className={cn(
              "text-3xl font-semibold tabular-nums",
              broken ? "text-text-subtle" : "text-text",
            )}
          >
            {data.currentStreak}
            <span className="ml-1 text-base font-medium text-text-muted">
              {data.currentStreak === 1 ? "day" : "days"}
            </span>
          </p>
          <p data-testid="streak-longest" className="text-sm text-text-muted">
            Longest streak: {data.longestStreak}
          </p>
        </div>
      </div>
      <p
        data-testid="streak-status"
        data-status={data.streakStatus}
        role="status"
        aria-live="polite"
        className="text-sm text-text-muted"
      >
        {STATUS_COPY[data.streakStatus] ?? ""}
      </p>
    </div>
  );
}

function ProgressList({ items }: { items: Array<ProgressItemRead> }) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-3">
      {items.map((item) => (
        <LinearProgress
          key={item.key}
          value={pct(item.current, item.target)}
          label={`${item.label} · ${item.current}/${item.target}`}
        />
      ))}
    </div>
  );
}

function BadgeGrid({
  earned,
  locked,
}: {
  earned: Array<EarnedBadgeRead>;
  locked: Array<LockedBadgeRead>;
}) {
  if (earned.length === 0 && locked.length === 0) {
    return (
      <EmptyState
        title="No badges yet"
        description="Study a summary, complete a quiz, or save a glossary term to start earning badges."
        headingLevel={3}
      />
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {earned.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">
            Earned
          </h3>
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {earned.map((badge) => (
              <li key={`${badge.badgeKey}-${badge.scopeId}`} data-testid={`badge-earned-${badge.badgeKey}`}>
                <Card className="flex h-full flex-col gap-1">
                  <span aria-hidden="true" className="text-2xl">
                    {glyph(badge.icon)}
                  </span>
                  <p className="text-sm font-medium text-text">{badge.title}</p>
                  <p className="text-xs text-text-muted">{badge.description}</p>
                  <Badge tone="success" className="mt-auto w-fit">
                    Earned
                  </Badge>
                </Card>
              </li>
            ))}
          </ul>
        </div>
      )}
      {locked.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">
            Locked
          </h3>
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {locked.map((badge) => (
              <li
                key={`${badge.badgeKey}-${badge.scopeId}`}
                data-testid={`badge-locked-${badge.badgeKey}`}
              >
                <Card className="flex h-full flex-col gap-1">
                  <span aria-hidden="true" className="text-2xl opacity-50">
                    {glyph(badge.icon)}
                  </span>
                  <p className="text-sm font-medium text-text">{badge.title}</p>
                  <p className="text-xs text-text-muted">{badge.description}</p>
                  <div className="mt-auto" data-testid={`badge-progress-${badge.badgeKey}`}>
                    <LinearProgress
                      value={pct(badge.current, badge.target)}
                      label={`${badge.current}/${badge.target}`}
                    />
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
