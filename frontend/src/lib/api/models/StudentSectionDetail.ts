/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { StudentAssetMeta } from './StudentAssetMeta';
export type StudentSectionDetail = {
    id: string;
    title: string;
    type: string;
    orderIndex: number;
    dueAt: (string | null);
    lecturerNotes: (string | null);
    assets: Array<StudentAssetMeta>;
};
