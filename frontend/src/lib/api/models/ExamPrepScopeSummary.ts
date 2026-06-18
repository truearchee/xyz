/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * A lecturer AssessmentScope as a student sees it (+ its current availability).
 */
export type ExamPrepScopeSummary = {
    id: string;
    name: string;
    coveredWeeks: Array<number>;
    available: boolean;
    reasonCode?: (string | null);
};
