/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type AgentRunRead = {
    id: string;
    triggerType: string;
    scopeType: string;
    scopeId: (string | null);
    scheduledFor: string;
    triggeredByUserId: (string | null);
    algorithmVersion: string;
    status: string;
    startedAt: (string | null);
    completedAt: (string | null);
    snapshotCount: number;
    recommendationCount: number;
    planCount: number;
    idempotencyKey: string;
    failureMessageSanitized: (string | null);
    createdAt: string;
    updatedAt: string;
};
