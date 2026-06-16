/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ModuleScheduleInput } from './ModuleScheduleInput';
export type CreateModuleRequest = {
    title: string;
    description?: (string | null);
    ownerId: string;
    timezone?: string;
    schedule: ModuleScheduleInput;
};
