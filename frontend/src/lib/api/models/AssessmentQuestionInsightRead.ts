/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AssessmentDistractorInsightRead } from './AssessmentDistractorInsightRead';
export type AssessmentQuestionInsightRead = {
    questionKey: string;
    questionText: string;
    answerCount: number;
    correctCount: number;
    incorrectCount: number;
    correctRatePercent: (string | null);
    smallCohort: boolean;
    smallCohortMessage: (string | null);
    distractors: Array<AssessmentDistractorInsightRead>;
};
