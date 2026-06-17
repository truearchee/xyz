/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Whether a recap/exam-prep span is startable (D3 all-or-wait), and what is still processing.
 */
export type ScopeAvailabilityResponse = {
    available: boolean;
    reasonCode?: (string | null);
    readySectionCount?: number;
    processingSectionCount?: number;
};
