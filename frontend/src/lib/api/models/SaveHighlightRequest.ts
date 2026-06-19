/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConversationSaveSource } from './ConversationSaveSource';
export type SaveHighlightRequest = {
    moduleSectionId?: (string | null);
    conversation?: (ConversationSaveSource | null);
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
