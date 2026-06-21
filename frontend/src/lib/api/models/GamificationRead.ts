/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EarnedBadgeRead } from './EarnedBadgeRead';
import type { LockedBadgeRead } from './LockedBadgeRead';
import type { ProgressItemRead } from './ProgressItemRead';
export type GamificationRead = {
    currentStreak: number;
    longestStreak: number;
    todayIsScheduled: boolean;
    todaySatisfied: boolean;
    nextScheduledDay: (string | null);
    streakStatus: string;
    earnedBadges: Array<EarnedBadgeRead>;
    lockedBadges: Array<LockedBadgeRead>;
    progressItems: Array<ProgressItemRead>;
    newBadgeIds: Array<string>;
    lastSeenAt: (string | null);
};
