/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaintenanceRunRead = {
    id: string;
    runType: string;
    mode: string;
    status: string;
    triggeredByUserId: (string | null);
    startedAt: string;
    completedAt: (string | null);
    summaryJson: (Record<string, any> | null);
    errorMessage: (string | null);
    createdAt: string;
};
