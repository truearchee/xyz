/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One row of the Workspace conversation list (Stage 8.4). ``display_title`` is derived-on-read (the
 * manual title when set, else the lecture/lab title, else a mode-derived fallback) so old null-title rows
 * render with no backfill; ``grounding_chip`` is "Lecture grounded" for the lecture chat and a mode label
 * otherwise. Excludes soft-deleted AND access-revoked conversations (invariant C) — the list query is the
 * 4.7 gate. 8.6c: time-management has no module/section/scope binding, so ``module_id`` and
 * ``module_title`` are nullable for that mode only.
 */
export type ConversationListItem = {
    id: string;
    conversationKind: string;
    displayTitle: string;
    moduleId?: (string | null);
    moduleTitle?: (string | null);
    attachedSectionId?: (string | null);
    sectionTitle?: (string | null);
    sectionType?: (string | null);
    assessmentScopeId?: (string | null);
    assessmentScopeName?: (string | null);
    coveredWeeks?: (Array<number> | null);
    lastMessagePreview?: (string | null);
    lastActivityAt: string;
    messageCount: number;
    groundingChip: string;
};
