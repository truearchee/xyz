/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type StartPracticeRequest = {
    scope: StartPracticeRequest.scope;
    subjectId?: (string | null);
    mode: StartPracticeRequest.mode;
};
export namespace StartPracticeRequest {
    export enum scope {
        COURSE = 'course',
        ALL = 'all',
    }
    export enum mode {
        FLASHCARD = 'flashcard',
        MULTIPLE_CHOICE = 'multiple_choice',
    }
}
