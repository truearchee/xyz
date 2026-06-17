/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * A recap span within one module — EITHER ``weeks`` OR a ``startDate``/``endDate`` range.
 */
export type RecapScopeRequest = {
    weeks?: (Array<number> | null);
    startDate?: (string | null);
    endDate?: (string | null);
};
