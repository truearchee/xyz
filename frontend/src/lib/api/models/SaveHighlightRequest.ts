/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SaveHighlightRequest = {
    moduleSectionId: string;
    term: string;
    selectedText?: (string | null);
    entryType?: SaveHighlightRequest.entryType;
};
export namespace SaveHighlightRequest {
    export enum entryType {
        TERM = 'term',
        CONCEPT = 'concept',
        FORMULA = 'formula',
    }
}
