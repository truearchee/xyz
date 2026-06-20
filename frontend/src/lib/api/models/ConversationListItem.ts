/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One row of the Workspace conversation list (Stage 8.4). ``display_title`` is derived-on-read (the
 * manual title when set, else the lecture/lab title, else a mode-derived fallback) so old null-title rows
 * render with no backfill; ``grounding_chip`` is "Lecture grounded" for the lecture chat and a mode label
 * otherwise. Excludes soft-deleted AND access-revoked conversations (invariant C) — the list query is the
 * 4.7 gate. 8.6a: a module-bound homework conversation has NO section, so the section fields are nullable
 * and ``module_id``/``module_title`` are always present.
 */
export type ConversationListItem = {
    id: string;
    conversationKind: string;
    displayTitle: string;
    moduleId: string;
    moduleTitle: string;
    attachedSectionId?: (string | null);
    sectionTitle?: (string | null);
    sectionType?: (string | null);
    lastMessagePreview?: (string | null);
    lastActivityAt: string;
    messageCount: number;
    groundingChip: string;
};
