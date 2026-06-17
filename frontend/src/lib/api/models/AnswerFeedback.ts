/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Immediate per-answer feedback. ``selectedAnswerOptionId`` is the ORIGINAL selected option, so a
 * duplicate submit (``alreadyAnswered=True``) returns the original result, never the resubmitted one.
 */
export type AnswerFeedback = {
    questionId: string;
    selectedAnswerOptionId: string;
    isCorrect: boolean;
    correctAnswerOptionId: string;
    explanation?: (string | null);
    alreadyAnswered?: boolean;
    mistakeSaved?: boolean;
};
