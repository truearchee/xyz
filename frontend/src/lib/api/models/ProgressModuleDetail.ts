/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BenchmarkRead } from './BenchmarkRead';
import type { ForecastRead } from './ForecastRead';
import type { TopicMasteryRead } from './TopicMasteryRead';
import type { TrendPointRead } from './TrendPointRead';
export type ProgressModuleDetail = {
    moduleId: string;
    title: string;
    currentStanding: (string | null);
    currentLetterGrade: (string | null);
    targetLetterGrade: (string | null);
    availableTargetGrades: Array<string>;
    forecast: (ForecastRead | null);
    trend: Array<TrendPointRead>;
    topics: Array<TopicMasteryRead>;
    benchmark: (BenchmarkRead | null);
};
