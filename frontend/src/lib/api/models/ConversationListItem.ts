/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One row of the Workspace conversation list (Stage 8.4). ``display_title`` is derived-on-read (the
 * manual title when set, else the lecture/lab title) so old null-title rows render with no backfill;
 * ``grounding_chip`` is the constant "Lecture grounded" in Option A (no ungrounded chat). Excludes
 * soft-deleted AND access-revoked conversations (invariant C) — the list query is the 4.7 gate.
 */
export type ConversationListItem = {
    id: string;
    displayTitle: string;
    moduleId: string;
    moduleTitle: string;
    attachedSectionId: string;
    sectionTitle: string;
    sectionType: string;
    lastMessagePreview?: (string | null);
    lastActivityAt: string;
    messageCount: number;
    groundingChip: string;
};
