/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ModuleMemberResponse = {
    membershipId: string;
    userId: string;
    moduleId: string;
    email: string;
    fullName: string;
    role: ModuleMemberResponse.role;
    membershipStatus: string;
    userIsActive: boolean;
    createdAt: string;
};
export namespace ModuleMemberResponse {
    export enum role {
        LECTURER = 'lecturer',
        STUDENT = 'student',
    }
}
