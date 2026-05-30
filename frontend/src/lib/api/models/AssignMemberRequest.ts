/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type AssignMemberRequest = {
    userId: string;
    role: AssignMemberRequest.role;
};
export namespace AssignMemberRequest {
    export enum role {
        STUDENT = 'student',
        LECTURER = 'lecturer',
    }
}
