/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SessionPatternEntry = {
    weekday: SessionPatternEntry.weekday;
    sectionType: SessionPatternEntry.sectionType;
};
export namespace SessionPatternEntry {
    export enum weekday {
        MONDAY = 'monday',
        TUESDAY = 'tuesday',
        WEDNESDAY = 'wednesday',
        THURSDAY = 'thursday',
        FRIDAY = 'friday',
        SATURDAY = 'saturday',
        SUNDAY = 'sunday',
    }
    export enum sectionType {
        LECTURE = 'lecture',
        LAB = 'lab',
    }
}
