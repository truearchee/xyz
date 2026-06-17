/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PracticeItem } from './PracticeItem';
export type PracticeSessionState = {
    sessionId: string;
    mode: string;
    scope: string;
    subjectId: (string | null);
    status: string;
    items: Array<PracticeItem>;
    totalCount: (number | null);
    correctCount: (number | null);
    notKnownCount: (number | null);
};
