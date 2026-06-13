/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One slot's state + content. ``content`` is non-null ONLY when ``state == 'ready'``.
 */
export type StudentSummarySlot = {
    state: string;
    content?: (string | null);
    /**
     * F-4.5-50: true when generated from a TRUNCATED transcript (first portion only). Surfaced in the
     * inline frame — never silent.
     */
    truncated?: boolean;
};
