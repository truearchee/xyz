/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Stage 8.5 — the discriminated assistant-chat save source. The student highlighted the term in a
 * completed assistant reply; the server verifies the message and derives subject/folder from the
 * conversation's bound section (never trusted from the client).
 */
export type ConversationSaveSource = {
    conversationId: string;
    messageId: string;
};
