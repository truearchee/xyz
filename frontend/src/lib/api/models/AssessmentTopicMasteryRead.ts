/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AssessmentTopicMasteryRowRead } from './AssessmentTopicMasteryRowRead';
export type AssessmentTopicMasteryRead = {
    available: boolean;
    unavailableReason: (string | null);
    unmappedAnswerCount: number;
    unmappedMessage: (string | null);
    rows: Array<AssessmentTopicMasteryRowRead>;
};
