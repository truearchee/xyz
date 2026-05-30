/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CreateUserRequest = {
    email: string;
    fullName: string;
    role: CreateUserRequest.role;
    password: string;
    timezone?: string;
};
export namespace CreateUserRequest {
    export enum role {
        STUDENT = 'student',
        LECTURER = 'lecturer',
        ADMIN = 'admin',
    }
}

