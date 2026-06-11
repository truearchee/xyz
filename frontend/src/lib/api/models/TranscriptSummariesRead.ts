/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BriefSummaryContent } from './BriefSummaryContent';
import type { DetailedSummaryContent } from './DetailedSummaryContent';
import type { TranscriptProcessingStatus } from './TranscriptProcessingStatus';
export type TranscriptSummariesRead = {
    status: TranscriptProcessingStatus;
    brief: (BriefSummaryContent | null);
    detailed: (DetailedSummaryContent | null);
    briefGeneratedAt: (string | null);
    detailedGeneratedAt: (string | null);
};
