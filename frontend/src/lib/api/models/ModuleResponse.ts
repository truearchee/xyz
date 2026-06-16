/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SessionPatternEntry } from './SessionPatternEntry';
export type ModuleResponse = {
    id: string;
    title: string;
    description: (string | null);
    ownerId: string;
    timezone: string;
    startsOn: (string | null);
    endsOn: (string | null);
    weekStartDay: ('monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday' | null);
    sessionPattern: (Array<SessionPatternEntry> | null);
    quizDay: ('monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday' | null);
    isActive: boolean;
    createdAt: string;
};
