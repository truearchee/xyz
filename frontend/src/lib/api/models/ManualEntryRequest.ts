/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManualEntryRequest = {
    subjectId: string;
    term: string;
    folderId?: (string | null);
    entryType?: ManualEntryRequest.entryType;
};
export namespace ManualEntryRequest {
    export enum entryType {
        TERM = 'term',
        CONCEPT = 'concept',
        FORMULA = 'formula',
    }
}
