/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MessageRead } from './MessageRead';
/**
 * The user message (saved first) + the pending assistant reply the client polls for.
 */
export type SendMessageResponse = {
    userMessage: MessageRead;
    assistantMessage: MessageRead;
};
