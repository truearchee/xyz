/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { RiskReasonRead } from './RiskReasonRead';
export type LecturerRosterRiskRow = {
    studentId: string;
    studentName: string;
    studentEmail: string;
    moduleId: string;
    riskTier: string;
    riskLabel: string;
    riskReasons: Array<RiskReasonRead>;
    algorithmVersion: string;
    inputHash: string;
    sourceCutoffAt: string;
    computedAt: string;
};
