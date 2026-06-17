/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { StudentMaterialMeta } from './StudentMaterialMeta';
import type { StudentSectionSummaryStates } from './StudentSectionSummaryStates';
export type StudentSectionRead = {
    id: string;
    title: string;
    type: string;
    orderIndex: number;
    dueAt: (string | null);
    lecturerNotes: (string | null);
    materials: Array<StudentMaterialMeta>;
    summaries: StudentSectionSummaryStates;
};
