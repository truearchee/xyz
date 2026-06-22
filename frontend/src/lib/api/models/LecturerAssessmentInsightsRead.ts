/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AssessmentAgentRunRead } from './AssessmentAgentRunRead';
import type { AssessmentQuestionInsightRead } from './AssessmentQuestionInsightRead';
import type { AssessmentTopicMasteryRead } from './AssessmentTopicMasteryRead';
export type LecturerAssessmentInsightsRead = {
    moduleId: string;
    moduleTitle: string;
    latestAgentRun: (AssessmentAgentRunRead | null);
    smallCohortThreshold: number;
    smallCohortMessage: string;
    questions: Array<AssessmentQuestionInsightRead>;
    mostMissedQuestions: Array<AssessmentQuestionInsightRead>;
    topicMastery: AssessmentTopicMasteryRead;
};
