/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AIProvenanceRead } from './AIProvenanceRead';
export type RecommendationRead = {
    id: string;
    reasonCode: string;
    targetKey: string;
    targetLabel: string;
    lecturerState: string;
    studentState: string;
    aiStatus: string;
    lecturerDraftText: string;
    lecturerDraftSource: string;
    studentNudgeText: string;
    studentNudgeSource: string;
    studentNextStep: string;
    deterministicPayload: Record<string, any>;
    aiProvenance?: (AIProvenanceRead | null);
    createdAt: string;
    updatedAt: string;
};
