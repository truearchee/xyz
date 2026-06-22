/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { RecommendationRead } from './RecommendationRead';
import type { RiskReasonRead } from './RiskReasonRead';
export type LecturerStudentRecommendationsRead = {
    studentId: string;
    studentName: string;
    studentEmail: string;
    moduleId: string;
    moduleTitle: string;
    riskReasons: Array<RiskReasonRead>;
    recommendations: Array<RecommendationRead>;
};
