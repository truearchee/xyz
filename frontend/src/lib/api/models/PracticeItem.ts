/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PracticeOption } from './PracticeOption';
export type PracticeItem = {
    entryId: string;
    displayOrder: number;
    term: string;
    definition: (string | null);
    language: string;
    options: (Array<PracticeOption> | null);
    answered: boolean;
    selectedEntryId: (string | null);
    isCorrect: (boolean | null);
    outcome: (string | null);
};
