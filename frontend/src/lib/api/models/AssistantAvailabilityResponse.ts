/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Whether the lecture assistant can be started for this section (decision 9).
 *
 * ``state`` ∈ {``ready``, ``processing``, ``unavailable``}. The UI shows "Start chat" only on
 * ``ready`` and reuses the summary processing/unavailable treatment otherwise.
 */
export type AssistantAvailabilityResponse = {
    state: string;
};
