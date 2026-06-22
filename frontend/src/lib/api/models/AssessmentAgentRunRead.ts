/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type AssessmentAgentRunRead = {
    id: string;
    status: string;
    scopeType: string;
    scopeId: (string | null);
    scheduledFor: string;
    completedAt: (string | null);
    snapshotCount: number;
    recommendationCount: number;
};
