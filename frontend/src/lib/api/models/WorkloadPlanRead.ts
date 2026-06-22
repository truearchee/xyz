/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WorkloadPlanItemRead } from './WorkloadPlanItemRead';
export type WorkloadPlanRead = {
    id: string;
    moduleId: string;
    algorithmVersion: string;
    inputHash: string;
    availabilityVersion: number;
    sourceCutoffAt: string;
    isActive: boolean;
    supersededAt: (string | null);
    provenance: Record<string, any>;
    createdAt: string;
    updatedAt: string;
    items: Array<WorkloadPlanItemRead>;
};
