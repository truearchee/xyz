/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MessageRead = {
    id: string;
    role: string;
    status: string;
    content?: (string | null);
    groundingStatus?: (string | null);
    answerBasis?: (string | null);
    retryable?: boolean;
    failureMessage?: (string | null);
    createdAt: string;
};
