/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WorkloadPlanItemRead = {
    id: string;
    taskKey: string;
    sourceSectionId: (string | null);
    scheduledDate: (string | null);
    window: (string | null);
    scheduledStartAt: (string | null);
    scheduledEndAt: (string | null);
    label: string;
    estimateMinutes: number;
    reason: string;
    sourceReasonCode: (string | null);
    sourceMetadata: Record<string, any>;
    tight: boolean;
    tightMessage: (string | null);
    sortIndex: number;
};
