/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BriefSummaryContent } from './BriefSummaryContent';
import type { DetailedSummaryContent } from './DetailedSummaryContent';
export type ActiveSummaryPreviewRead = {
    activeTranscriptId: string;
    brief: (BriefSummaryContent | null);
    detailed: (DetailedSummaryContent | null);
    briefEligible: boolean;
    detailedEligible: boolean;
    hasPendingReplacement: boolean;
};
