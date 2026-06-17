/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ModuleSectionPreview = {
    title: string;
    type: ModuleSectionPreview.type;
    orderIndex: number;
    weekNumber: number;
    sessionDate: string;
};
export namespace ModuleSectionPreview {
    export enum type {
        LECTURE = 'lecture',
        LAB = 'lab',
    }
}
