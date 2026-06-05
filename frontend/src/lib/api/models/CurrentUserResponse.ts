/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActiveModuleMembership } from './ActiveModuleMembership';
export type CurrentUserResponse = {
    userId: string;
    email: string;
    fullName: string;
    role: CurrentUserResponse.role;
    timezone: string;
    activeModuleMemberships: Array<ActiveModuleMembership>;
};
export namespace CurrentUserResponse {
    export enum role {
        ADMIN = 'admin',
        LECTURER = 'lecturer',
        STUDENT = 'student',
    }
}
