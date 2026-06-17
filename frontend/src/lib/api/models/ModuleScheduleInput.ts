/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SessionPatternEntry } from './SessionPatternEntry';
/**
 * Creation-time schedule (Stage 5.5, D1/D10). Course dates are calendar dates (YYYY-MM-DD),
 * never JS timestamps. weekStartDay defaults to Monday. sessionPattern drives generation; the quiz
 * day is recorded but generates no section here.
 */
export type ModuleScheduleInput = {
    courseStartDate: string;
    courseEndDate: string;
    weekStartDay?: ModuleScheduleInput.weekStartDay;
    sessionPattern: Array<SessionPatternEntry>;
    quizDay?: ('monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday' | null);
};
export namespace ModuleScheduleInput {
    export enum weekStartDay {
        MONDAY = 'monday',
        TUESDAY = 'tuesday',
        WEDNESDAY = 'wednesday',
        THURSDAY = 'thursday',
        FRIDAY = 'friday',
        SATURDAY = 'saturday',
        SUNDAY = 'sunday',
    }
}
