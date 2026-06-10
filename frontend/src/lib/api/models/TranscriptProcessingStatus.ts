/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TranscriptProcessingSteps } from './TranscriptProcessingSteps';
export type TranscriptProcessingStatus = {
    activeTranscriptId: string;
    transcriptStatus: string;
    overallState: string;
    currentPhase: (string | null);
    failedStep: (string | null);
    steps: TranscriptProcessingSteps;
    segmentCount: number;
    chunkCount: number;
    embeddedChunkCount: number;
    safeFailureMessage: (string | null);
    updatedAt: string;
};
