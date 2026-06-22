/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { StudentRiskReasonRead } from './StudentRiskReasonRead';
export type StudentRiskRead = {
    studentId: string;
    moduleId: string;
    riskReasons: Array<StudentRiskReasonRead>;
    algorithmVersion: string;
    inputHash: string;
    sourceCutoffAt: string;
    computedAt: string;
};
